# FACET

**F**ailure **A**nalysis, **C**haracterisation & **E**valuation **T**oolkit for
instance segmentations of medical images.

FACET takes a segmentation label map (and optionally the scan it came from),
derives a description of it, and judges that description against what a correct
segmentation should look like. It is built around the premise that segmentation
tools fail in *characteristic, nameable ways* — and that those failure modes are
worth cataloguing, generating on demand, and measuring individually rather than
collapsing into a single quality score.

Applied here to 3D spine/vertebra segmentation, a task with well-known failure
modes: heterogeneous modalities and resolutions, variable field of view, normal
and pathological appearance variation, and inconsistent labelling (e.g. T13 vs
L1).

## What it does

- **Extract** — geometric, topological and intensity features from an instance
  label map: per-label volume/extent/bbox, connected components and
  fragmentation, centroids, a spline fit through the spinal curve and per-vertebra
  offsets from it, orientation and curvature, inter-vertebra spacing and ordering,
  first-order intensity statistics (optionally PyRadiomics).
- **Perturb** — fabricate deliberately-broken label maps from clean ones, each
  carrying a machine-readable record of *what was broken*: fragmentation, fusion,
  stray islands, missing levels, border truncation, overlap, displacement,
  relabelling and sequence breaks. This is the stress-test corpus that makes
  detection claims quantitative.
- **Score** — compare a case against reference feature distributions built from
  ground-truth cohorts (VerSe), stratified by anatomical level and subject size.
- **Judge** — an explainable rule engine turns those features into a verdict
  (pass / flagged-for-review / fail) where **every flag carries a reason**,
  emitted as both JSON and a human-readable report.
- **Evaluate** — a cohort-level harness comparing verdicts, overlap (Dice) and
  feature divergence against ground truth, with threshold calibration.

Explainability is a design constraint, not a feature: a heuristic you can inspect
and argue with is preferred over a black-box score you cannot.

## Status

Pre-alpha research code. The feature extraction, perturbation and reporting
layers are mature and well covered by tests; the normative scoring model is
under active rework. Interfaces may change without notice.

## Data

Reference distributions are built from **VerSe** (<https://github.com/anjany/verse>),
355 CT scans with semantic vertebra segmentations; a subset carries vertebral
fracture gradings (<https://osf.io/4skx2/files/zy68u>). No dataset is bundled —
cohorts are supplied via the dataset adapters in `segfacet.datasets`.

FACET is segmentation-tool agnostic: it consumes label maps in a documented,
overridable label convention rather than any one segmenter's internals.

## Origin

Began at the BMEIS Hackathon 2026 as an XNAT-deployed QC gate, and doubles as a
practical exercise in specification-driven, AI-assisted development
(see [`.aide/`](.aide/README.md)).

## Licence

MIT — see [LICENSE](LICENSE).

## GitHub Repository

https://github.com/dadrobny/segfacet

## Development setup

`segfacet` is a Python 3.9+ package using a `src/` layout and a `pyproject.toml`
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

After installing, the `segfacet` console script is available:

```bash
segfacet --help             # top-level usage, lists the subcommands
segfacet --version          # print the package version

segfacet run --scan scan.nii.gz --seg seg.nii.gz --out out/    # QC one case
segfacet build-reference --cohort cohort/ --out reference.json  # fit reference distributions
segfacet evaluate --cohort manifest.json --out out/            # cohort metrics (+ --calibrate)
```

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
