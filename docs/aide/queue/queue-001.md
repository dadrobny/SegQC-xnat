# Seg-QC-xnat — Work Queue 001

> **Status:** Draft v1 · **Created:** 2026-06-24
> Step 4 of the AIDE workflow. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> This is the **first** queue; item numbering starts at 001.

---

## Scope of this queue

Covers roadmap **Stage 0 — Project Scaffolding & I/O Foundation** and
**Stage 1 — End-to-End Thin Slice: Empty Detection + Report** (objectives **G1**,
**G4**).

**Milestone delivered:** a runnable, cross-platform `segqc` package + CLI that
loads a scan and instance label map, normalises labels, and runs the smallest
*complete* pipeline (input → verdict → report) — detecting empty / trivially-
failed segmentations and emitting both JSON and human-readable reports. This is
the thin end-to-end slice every later stage plugs into.

**Prioritisation rationale.** The roadmap dependency graph is strictly linear
here (`0 → 1 → 2 → …`); nothing downstream can be built or tested until the
package skeleton, I/O, and report model exist. Stages 0 and 1 are each
deliberately "thin", so both fit in one ~week batch and produce an immediately
demonstrable result.

**Estimated size:** ~1 week (10 items). Each item is independently testable
locally with `pytest`.

**Sequencing note.** Items 001–006 complete Stage 0; items 007–010 complete
Stage 1. Within the batch, 001 → 003 → 004 → 006 form the critical path; 002
(fixtures) should land early since later items depend on it for tests.

---

## Work items

### Item 001: Package scaffolding & build configuration
Create the `segqc/` Python package targeting **Python 3.9+** with a
`pyproject.toml` declaring pinned core dependencies (NumPy, SciPy, scikit-image,
NiBabel and/or SimpleITK) and a console-script entry point registering the
`segqc` command. Establish the source layout, package metadata, and a minimal
`segqc --help` / `segqc run --help` that parses arguments and exits cleanly.
*Testable:* `pip install -e .` succeeds; `segqc --help` runs; an import smoke
test passes on Windows/macOS/Linux.

### Item 002: Test harness & synthetic NIfTI fixtures
Stand up the `pytest` harness (config, test directory, CI-friendly invocation)
and a small **synthetic NIfTI fixture builder** that generates tiny scan + label-
map pairs in-memory/on-disk (e.g. a few labelled blocks, an empty map, an
anisotropic-spacing case). These fixtures are reused by every subsequent item.
*Testable:* `pytest` collects and runs; fixture builder produces valid NIfTI
volumes with the expected shapes, labels, and affines.

### Item 003: NIfTI I/O loader
Implement loading of the scan and instance label map from NIfTI, preserving
**spacing/affine** and correctly handling **anisotropic** voxels. Expose a
clean in-memory representation (array + spacing + affine + label inventory)
that downstream feature/heuristic code consumes. Validate inputs and fail with
clear errors on malformed/missing files.
*Testable:* unit tests load fixtures, assert correct array shape, dtype,
spacing, affine, and that anisotropic spacing is faithfully represented.

### Item 004: Label-convention module
Implement the configurable mapping between integer labels and anatomical
vertebrae (C1–C7, T1–T12(+T13), L1–L5(+L6), S, …), shipping a **default
TotalSegmentator/VerSe** mapping and allowing an override via config. Provide
lookups in both directions and a label-inventory summariser (present labels →
anatomical names, with unknown-label handling).
*Testable:* unit tests assert default mapping round-trips, custom overrides
apply, and unknown/out-of-range labels are handled without crashing.

### Item 005: Structured logging & versioned heuristic-config scaffold
Add structured logging (configurable level, machine-parseable where useful) and
a **versioned heuristic-config** scaffold (YAML/JSON) with a loader, schema
version field, and sensible defaults. No heuristics yet — just the config
plumbing that Stage 4 will populate, plus reproducibility hooks (record
config version in outputs).
*Testable:* unit tests load a sample config, apply defaults for missing keys,
reject an unknown/incompatible schema version, and confirm log output is emitted.

### Item 006: CLI `segqc run` skeleton — load, inventory, stub JSON *(completes Stage 0)*
Wire the CLI `segqc run --scan <nii> --seg <nii> --out <dir>` to invoke the
loader (003) + label convention (004), print the **label inventory with
anatomical names**, and write a **stub JSON** to the output directory. This
satisfies the Stage 0 acceptance test end-to-end.
*Testable:* running `segqc run` on a fixture prints the labelled inventory and
writes a valid stub JSON; an end-to-end CLI test asserts exit code 0 and output
file contents. Runs CPU-only on all three platforms.

### Item 007: Empty / near-empty detection
Implement configurable detection of empty / trivially-failed segmentations: no
labels present, total foreground below **N** voxels, or fewer than **K**
distinct labels — all thresholds configurable via the heuristic config (005).
*Testable:* unit tests over fixtures confirm empty, near-empty (sub-threshold),
and populated maps are classified correctly across threshold settings.

### Item 008: QC verdict model
Define the QC verdict data model: per-case verdict of `pass` /
`flagged-for-review` / `fail`, carrying **per-case and per-vertebra reasons**
(each reason an explicit, human-readable string with offending labels). Provide
aggregation primitives so later heuristics can contribute reasons and the
overall verdict is derived by severity.
*Testable:* unit tests construct verdicts from reason sets and assert correct
overall verdict, severity ordering, and per-vertebra attribution.

### Item 009: JSON report schema v0 & serializer
Define the **versioned JSON report schema v0** (machine-readable) and a
serializer that emits the verdict model (008) plus case/label metadata and the
config version (005). Include schema validation so emitted reports are checked
in tests. This is the contract Stage 2 will extend with a `features` block.
*Testable:* serialised reports validate against the schema; round-trip and
golden-snapshot tests confirm stable, deterministic output.

### Item 010: Human-readable report renderer & final pipeline wiring *(completes Stage 1)*
Render a **human-readable report** (Markdown/plain text) from the same verdict
model (008), and wire the full Stage 1 pipeline in the CLI:
loader → empty-check (007) → verdict (008) → **both** JSON (009) and human
reports. This satisfies the Stage 1 acceptance: empty fixtures are flagged
`fail` with explicit reasons (**G1**); a populated fixture passes the empty
check; JSON validates and a human report is produced (**G4**).
*Testable:* end-to-end CLI tests assert correct verdict + both report artifacts
for empty, near-empty, and populated fixtures; empty-detection thresholds are
covered.

---

## Next Step

Pick an item from this queue (start with **Item 001**), then open a **new chat
session** and run `/speckit-aide-create-item` with that item's description to
produce a detailed work-item specification under `docs/aide/items/NNN-*.md`.
Per the team workflow in `CLAUDE.md`, branch per item
(`git switch -c aide/001-package-scaffolding`) and `git pull --rebase` before
starting.
