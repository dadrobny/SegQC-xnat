# SegQC deployment guide (Docker + XNAT Container Service)

This guide covers deploying **SegQC** — automated quality control for vertebra
instance segmentations of spine CT — as a Docker image and installing it as an
**XNAT Container Service** command, so it can run against real XNAT session
data. It closes Stage 9 of the project roadmap (see
[`docs/aide/roadmap.md`](aide/roadmap.md)): *"Container runs the pipeline on a
mounted case, producing JSON + human report; `command.json` validates; install
steps documented"*.

> **Validation status — read before relying on §2/§3.** The Docker half of this
> guide is verified for real: `docker build` and `docker run` on a mounted case
> run in CI on every change. The **XNAT half is not**. The install and
> input-configuration steps below are written from the official XNAT Container
> Service documentation and have **never been executed against a live XNAT
> server** — no session has been processed end-to-end, so expect drift and treat
> §2/§3 as a starting point rather than a tested procedure. Closing that gap is
> roadmap **Stage 15**; see the "XNAT Container Service command on a real server"
> row in [`docs/aide/progress.md`](aide/progress.md)'s verification table.

## Overview / prerequisites

- **CPU-only.** The image is a plain `python:3.11-slim` base with no GPU/CUDA
  layers or packages — any Docker host (including a stock XNAT Docker server)
  can run it. No GPU is required.
- **Bundled default reference artifact.** The image ships the default
  reference artifact (`src/segqc/reference/reference_default.json`) as package
  data, so `segqc run --reference` works out of the box with no extra mount —
  the optional `/input/reference` mount (see below) only matters if you want to
  *override* the bundled default.
- **What you need on the Docker/XNAT host:** Docker (or the XNAT-managed Docker
  server) able to pull/load the `segqc:latest` image, and access to a scan
  (image) and segmentation (label-map) NIfTI resource per session.

The four topics below map to the operator's actual workflow: build the image,
install `command.json` on XNAT, configure a session's inputs, and (optionally)
verify locally with `docker run` before touching a real XNAT server. A
troubleshooting section closes out the guide.

## 1. Build the image

Build the default (no-radiomics) image from the repo root:

```bash
docker build -t segqc:latest .
```

This produces a CPU-only image pinned against the committed `constraints.txt`
lockfile, with the default reference artifact bundled inside the installed
wheel.

To build the variant with the optional `pyradiomics`/SimpleITK extra enabled
(Stage-8 intensity/radiomics QC checks), pass the `INSTALL_RADIOMICS` build
arg:

```bash
docker build -t segqc:radiomics --build-arg INSTALL_RADIOMICS=1 .
```

`INSTALL_RADIOMICS` defaults to `0` (off); any of `1`/`true` enables it.

**No `ENTRYPOINT` is set on this image** — it deliberately leaves the
container's entry point open so the XNAT Container Service (see item 067's
`command.json`) can layer its own entry script on top. This means:

- `docker run <image> segqc <args>` invokes the `segqc` CLI console script
  directly (e.g. `docker run segqc:latest segqc --version`).
- The image's `CMD` defaults to `segqc --help` for ergonomic manual inspection,
  but is overridden by `command.json`'s `command-line`, which instead invokes
  the XNAT entry script (`python /app/docker/entrypoint.py ...`) described in
  §3 below.

## 2. Install `command.json` on an XNAT server

The repo-root [`command.json`](../command.json) declares the `segqc` XNAT
Container Service command: the scan/segmentation (+ optional config/reference)
mounts, the `reference-mode`/`intensity-mode` boolean inputs, the two output
report resources, and the `segqc-session` XNAT wrapper (external/derived
inputs and output handlers) that binds the command to an imaging session.

To install it on an XNAT server:

1. **Make the image available to the XNAT host's Docker server.** The image
   referenced by `command.json` (`"image": "segqc:latest"`) must exist on (or
   be pullable by) the Docker server XNAT's Container Service is configured
   against — e.g. `docker save segqc:latest | ... | docker load` on the XNAT
   host, push it to a registry the host can pull from, or build it directly on
   the host.
2. **Upload/enable the command via the Container Service admin UI.** In
   XNAT's Administer → Plugin Settings → Images and Commands (Container
   Service admin panel), add a new command from the image (XNAT reads the
   image's embedded label or accepts a pasted `command.json`), then **enable**
   the command for the relevant project(s)/site, and **enable** its
   `segqc-session` XNAT wrapper against the `xnat:imageSessionData` context so
   it appears as a runnable action on an imaging session.
3. **Follow the official XNAT Container Service documentation** for the exact
   click-path (it varies slightly by XNAT version):
   <https://wiki.xnat.org/container-service/building-docker-images-for-container-service>

Once enabled, `segqc` (label "SegQC") appears as a runnable command on any
session matching the `segqc-session` wrapper's context.

## 3. Configure inputs on a session

The `segqc-session` XNAT wrapper in `command.json` binds a single **session**
external input (the imaging session being QC'd) to a set of derived inputs
mounted into the container, plus two boolean mode toggles:

| Derived input        | Required | Mount path         | Purpose                                                                 |
|-----------------------|----------|---------------------|--------------------------------------------------------------------------|
| `scan-resource`       | yes      | `/input/scan`        | The session's scan (image) resource, mounted **read-only**.              |
| `seg-resource`        | yes      | `/input/seg`          | The session's segmentation label-map resource, mounted **read-only**.    |
| `config-resource`     | optional | `/input/config`       | Optional QC-config YAML override (bundled default used if absent).       |
| `reference-resource`  | optional | `/input/reference`    | Optional reference-artifact JSON override (bundled default used if absent).|

Each derived input resolves to exactly one file in its mount directory; the
entry script (`docker/entrypoint.py`) requires exactly one NIfTI file for
`scan`/`seg` and accepts at most one override file for `config`/`reference`.

Two boolean command inputs control which QC modes run:

- **`reference-mode`** — when enabled, adds `--reference` to the underlying
  `segqc run` invocation, turning on reference-grounded QC checks.
- **`intensity-mode`** — when enabled, adds `--intensity` to the underlying
  `segqc run` invocation, turning on the Stage-8 intensity/radiomics QC
  checks.

Both default to `false` (off) and can be toggled per-run from the "Run
Containers" launch dialog on the session, alongside picking which
scan/segmentation resource to use when a session has more than one.

**Outputs.** The command produces two output resources, written back
`as-a-child-of` the session under a resource labeled `SEGQC`:

- `segqc_report.json` — the machine-readable QC report.
- `segqc_report.txt` — the human-readable QC report.

Both land in the `/output` mount inside the container and are collected by
XNAT's output handlers once the run completes successfully.

## 4. Local verification

Before configuring anything on a real XNAT server, you can exercise the exact
same mount/argument contract locally with a plain `docker run`, using the same
paths `command.json` and `docker/entrypoint.py` use (this is the same
invocation the Stage-9 smoke/acceptance tests drive):

```bash
docker run --rm \
  -v /path/to/scan_dir:/input/scan:ro \
  -v /path/to/seg_dir:/input/seg:ro \
  -v /path/to/out_dir:/output \
  segqc:latest \
  python /app/docker/entrypoint.py \
    --scan-dir /input/scan --seg-dir /input/seg --out-dir /output
```

- `scan_dir` and `seg_dir` must each contain **exactly one** NIfTI file
  (`*.nii`/`*.nii.gz`, case-insensitive).
- `out_dir` must be writable by the container; on success it will contain both
  `segqc_report.json` and `segqc_report.txt`.
- To also exercise the optional overrides and mode toggles, add
  `-v /path/to/config_dir:/input/config:ro`,
  `-v /path/to/reference_dir:/input/reference:ro`, and append
  `--config-dir /input/config --reference-dir /input/reference --reference
  --intensity` to the entry-script invocation.

A successful run exits `0` and produces both report files; any input problem
(see §5) prints a single `Error: ...` line to stderr and exits non-zero, with
no output written.

## 5. Troubleshooting

`docker/entrypoint.py` resolves the mounted-directory inputs *before* the QC
pipeline runs, so any problem with a mount is caught early: it is reported as
a **single `Error: ...` line on stderr**, a **non-zero exit code**, **no raw
traceback**, and **no partial report** is left in `/output`.

| Failure mode                                   | Symptom                                                                 | Fix                                                                                     |
|--------------------------------------------------|--------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| Missing/empty input mount                        | `Error: no NIfTI file (*.nii/*.nii.gz) found in scan directory: ...` (or `segmentation directory`); non-zero exit, no traceback, no partial report | Confirm the session actually has a scan/segmentation resource and it was correctly bound to `scan-resource`/`seg-resource` before launching. |
| Ambiguous (multiple-NIfTI) input mount            | `Error: ambiguous scan directory ...: found N NIfTI files (...); expected exactly one`; non-zero exit, no traceback, no partial report | Point the resource selection at a single NIfTI file, or curate the resource so it contains only the intended scan/segmentation file. |
| Non-NIfTI input                                  | Same "no NIfTI file found" `Error: ...` message as the missing/empty case (a directory containing only non-NIfTI files is treated identically); non-zero exit, no traceback, no partial report | Ensure the mounted resource contains a `.nii`/`.nii.gz` file, not e.g. DICOM or another format. |
| Scan/segmentation grid (affine/shape) mismatch    | The pipeline itself reports a QC/validation error (surfaced the same way — non-zero exit, `Error: ...`, no partial report) rather than an entry-script mount error | Re-derive the segmentation from the same scan, or verify the scan and segmentation resources on the session actually correspond to the same acquisition/grid. |

If you hit anything not in this table, re-run locally per §4 to reproduce
outside XNAT — the entry script and pipeline behave identically in both
contexts, which makes local Docker runs the fastest way to troubleshoot.
