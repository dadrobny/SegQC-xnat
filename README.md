# SegQC-xnat
Segmentation Quality Control Pipeline for XNAT created during the BMEIS Hackathon 2026

## Team Members - Maximum of 5 people per project
- David (david.drobny@kcl.ac.uk)
- Liane
- Name 3
- Name 4
- Name 5

## Project Title

**SegQC-xnat**: Segmentation Quality Control Pipeline for XNAT

(_SQUAT: Segmentation QUality Assessment Tool?_)

## Overview

A Docker container deployable on XNAT that runs automated image segmentation, heuristic quality control, and generates a targeted report for human review.
Applied here to 3D spine/vertebra segmentation, a task with well-known failure modes: heterogeneous imaging modalities and resolutions, variable FoV, normal and pathological appearance variation, and inconsistent labelling (e.g. T13 vs. L1).
The project also serves as a practical exercise in specification driven development (https://github.com/github/spec-kit) and AI driven engineering (e.g. https://github.com/mnriem/spec-kit-aide-extension-demo).

### Extendability
Segmentation heuristics can support downstream classification tasks:
- vertebral segment (C/T/L/S),
- pathologies (e.g. compression fracture),
- implant presence (pedicle screws, rods, intervertebral cages),
- spinal shape (scoliosis)
Additional tools can be plugged in:
- registration-based template matching,
- radiomics or similar features,
- SSM's to extend feature space towards complex shape representations

### Transferability
The pipeline generalises to any application where automated segmentation has a high failure rate.

## Data

We are using the VerSe dataset as an example for vertebra segmentation.
- https://github.com/anjany/verse
- 355 CT scans with semantic vertebra segmentations
- for a subset, there are vertebral fracture gradings available (https://osf.io/4skx2/files/zy68u)

We use TotalSegmentator as a pre-trained model for vertebra segmentation
- https://github.com/wasserth/totalsegmentator
- good general purpose segmentation tool
- provides C1-5, T1-12, L1-5, and sacrum segmentations (does not accommodate variation in numbering of vertebral segments, e.g. T13)
  

## GitHub Repository

https://github.com/dadrobny/SegQC-xnat

## Development setup

`segqc` is a Python 3.9+ package using a `src/` layout and a `pyproject.toml`
build (hatchling). Develop against a clean virtual environment:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
#   Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
#   macOS / Linux:
source .venv/bin/activate

# 2. Install the package in editable mode with the dev extras (pytest)
pip install -e .[dev]

# 3. Run the test suite
pytest
```

After installing, the `segqc` console script is available:

```bash
segqc --help          # top-level usage, lists the `run` subcommand
segqc --version       # print the package version
segqc run --help      # usage for `run` (--scan / --seg / --out)
```

> Note: `segqc run` is currently a scaffold stub — it parses its arguments and
> exits without performing any I/O. The QC pipeline is wired up in later work
> items (see `docs/aide/`).

## Testing & synthetic fixtures

Tests use small, deterministic, in-memory **synthetic NIfTI** volumes so no real
imaging data is needed. The builders live in
[`tests/synthetic.py`](tests/synthetic.py) (plain functions — importable from
ad-hoc scripts too) and are exposed to test modules as pytest fixtures via
[`tests/conftest.py`](tests/conftest.py). Reuse these in new test modules rather
than rolling your own test data.

**Builder functions** (`from synthetic import ...`):

- `affine_from_spacing(spacing)` — 4×4 diagonal affine (voxel sizes on the
  diagonal, identity rotation, zero origin).
- `make_scan(shape, spacing=(1,1,1), *, dtype=int16, fill=0, gradient=False)` —
  intensity volume as a `Nifti1Image`.
- `make_labelmap(shape, blocks, spacing=(1,1,1))` — paints integer `blocks`
  (`{label: ((x0,x1),(y0,y1),(z0,z1))}`, half-open boxes; later boxes win on
  overlap) into a zero `uint16` volume.
- `write_nifti(img, path)` — save a `.nii` / `.nii.gz` (extension picks
  compression); returns the `Path`.
- Canonical cases returning a `SyntheticCase` bundle: `labelled_blocks_case()`
  (≥3 separated labels, isotropic 1 mm), `empty_case()` (all-zero label map),
  `anisotropic_case()` (non-uniform `(1,1,3)` mm spacing). `CANONICAL_CASES`
  maps names → builders.

**`SyntheticCase`** bundles `scan_img`, `seg_img` (`Nifti1Image`s) with
known-good metadata: `expected_labels`, `voxel_counts` (`{label: n_voxels}`),
`spacing`, `shape`. `case.write(dir, suffix=".nii.gz")` materialises it and
returns `(scan_path, seg_path)`.

**Pytest fixtures** (`conftest.py`): in-memory `labelled_blocks`,
`empty_labelmap`, `anisotropic` (yield a `SyntheticCase`); on-disk
`labelled_blocks_files`, `empty_labelmap_files`, `anisotropic_files` (write under
`tmp_path`, yield `(scan_path, seg_path)`).

```python
def test_example(labelled_blocks):
    assert labelled_blocks.expected_labels == {1, 2, 3}
    assert labelled_blocks.voxel_counts == {1: 64, 2: 64, 3: 64}
```

> Scope: these are **well-formed, happy-path** volumes (plus one empty case).
> The deliberately-broken failure corpus is Stage 5. The affine is a minimal
> diagonal one — faithful/oblique real-world affines are the loader item's (003)
> concern.
