# Reference-artifact build recipe

> Companion to [`docs/aide/dataset-verse19.md`](aide/dataset-verse19.md) (the
> real-VerSe layout/naming facts) and the item-082 spec
> ([`docs/aide/items/082-real-verse-build-recipe.md`](aide/items/082-real-verse-build-recipe.md)).
> This document is the **recipe + policy**; it adds no code. The build
> machinery it drives (`segqc build-reference`, `ingest_cohort`,
> `build_reference`, `write_artifact`, `load_artifact`) already exists
> (items 044/045/063/081).

## Overview

The project ships and consumes **two** reference-data artifacts:

1. **The committed synthetic default** — `src/segqc/reference/reference_default.json`.
   Built from a fixed, seeded, no-wall-clock synthetic cohort
   (`segqc.reference.artifact.build_default_cohort`) via
   `python -m segqc.reference.artifact`. This is the **test/determinism
   baseline**: it is byte-reproducible across platforms and runs, and Stage
   6/8 determinism tests depend on it never changing shape unexpectedly. It
   is not a stand-in for real anatomical grounding.
2. **A separately versioned real-VerSe artifact** —
   `reference_verse_vN.json` (e.g. `reference_verse_v1.json`), with
   `provenance.source == "verse-vN"` (e.g. `"verse-v1"`). Built from a real
   mounted VerSe ground-truth cohort via `segqc build-reference` (see
   *Build invocation* below). This is the artifact that grounds the
   delta-to-reference machinery in real anatomy.

The real-VerSe artifact is **additive** — it never overwrites or replaces
`reference_default.json`.

## Storage & versioning policy

- **Raw VerSe scans (and any other real-cohort NIfTI data) are never
  committed to this repo.** They are large binary blobs and/or
  licensed/restricted data; git is the wrong storage layer for them. This
  mirrors the existing policy in `docs/aide/dataset-verse19.md` for the raw
  `dataset-verse19training/` download.
- **Only the derived distributions artifact is committed** — the small JSON
  file produced by `write_artifact` (per-level feature statistics +
  provenance), never the source scans/masks it was built from.
- **The committed synthetic `reference_default.json` is retained, not
  replaced.** A real-VerSe build does **not** overwrite the bundled default;
  it is written to its own versioned filename and shipped alongside it.
- **Versioned naming convention:** `reference_verse_vN.json`, with
  `provenance.source == "verse-vN"` (`N` = 1, 2, 3, … incrementing on each
  new real build, e.g. after a larger cohort or a schema bump). When an
  actual real-VerSe artifact is built by a data-holding human or CI runner,
  it is committed under `src/segqc/reference/` as package data (so it ships
  importable/selectable by path alongside the default), and its filename
  pattern should be pinned `text eol=lf` in `.gitattributes` for CRLF
  hygiene on Windows checkouts (see the Gotchas note in the project
  `CLAUDE.md`). **This item commits no such file** — see the fenced scope
  in the item-082 spec.

## Acquisition

Real VerSe ground truth comes from the **VerSe19** training release:

- **Source:** `dataset-verse19training.zip` from
  `https://s3.bonescreen.de/public/VerSe-complete/`.
- **DOI:** `10.17605/OSF.IO/NQJYW`.
- Full layout, naming convention, label mapping, and size/count facts are
  documented in [`docs/aide/dataset-verse19.md`](aide/dataset-verse19.md) —
  read that living reference first; this document only restates what is
  needed to stage a build.

Per that reference, the dataset root (after unzipping) is
`dataset-verse19training/dataset-verse19training/`, with:

```
rawdata/sub-verseNNN/sub-verseNNN_ct.nii.gz
derivatives/sub-verseNNN/sub-verseNNN_seg-vert_msk.nii.gz
```

(plus split-subject `_split-verseMMM` infixes, centroid JSON, and preview
PNGs that the build recipe does not need).

## Staging the cohort for ingestion

`segqc.reference.ingest.ingest_cohort` was built for item 044's flat,
**non-recursive** convention: it lists a single `--cohort` directory with
`os.listdir` (no recursive walk of subdirectories) looking for files ending
in `--seg-suffix`, and for each match hardcodes the sibling scan filename as
`<id>_scan.nii.gz` (there is no `--scan-suffix` flag). Real VerSe's on-disk
layout does not match this directly — masks live nested under
`derivatives/sub-verseNNN/`, and CT scans are named `..._ct.nii.gz`, not
`..._scan.nii.gz`. No code adapter is added for this (see Assumption Q3 in
the item-082 spec); instead, an operator **stages** the cohort into one flat
directory before invoking the build:

1. **Flatten the masks.** Copy or symlink every
   `derivatives/sub-verseNNN/sub-verseNNN_seg-vert_msk.nii.gz` (and any
   `_split-verseMMM` variants) out of its nested `derivatives/sub-verseNNN/`
   subdirectory into one flat staging directory, keeping the filename as-is
   (the real VerSe mask suffix `_seg-vert_msk.nii.gz` is passed straight
   through to `--seg-suffix`).
2. **Provide each CT as a `<id>_scan.nii.gz` sibling.** Rename or
   (symlink-)link each `rawdata/sub-verseNNN/sub-verseNNN_ct.nii.gz` into the
   same staging directory as `sub-verseNNN_scan.nii.gz`, so `ingest_cohort`'s
   hardcoded sibling-scan discovery finds it and folds intensity features in.

A minimal staging script (illustrative, not part of this repo's production
code — the recipe is manual per the item-082 scope):

```bash
mkdir -p staged_verse
for d in dataset-verse19training/dataset-verse19training/derivatives/sub-verse*/; do
    sub=$(basename "$d")
    cp "$d/${sub}_seg-vert_msk.nii.gz" "staged_verse/"
    cp "dataset-verse19training/dataset-verse19training/rawdata/${sub}/${sub}_ct.nii.gz" \
       "staged_verse/${sub}_scan.nii.gz"
done
```

Adjust for split-subject `_split-verseMMM` infixes as needed; the exact
staging mechanics (script vs. manual copy vs. symlinks) are an operator
choice — the requirement is only that the staged directory be flat and that
each mask have a `<id>_scan.nii.gz` sibling.

## Build invocation

Once staged, drive the existing `segqc build-reference` CLI directly — no
new code, no wrapper:

```bash
segqc build-reference \
    --cohort staged_verse \
    --out src/segqc/reference/reference_verse_v1.json \
    --source verse-v1 \
    --build-date 2026-07-15 \
    --seg-suffix _seg-vert_msk.nii.gz
```

- `--seg-suffix _seg-vert_msk.nii.gz` is the only flag needed to handle
  VerSe's mask naming; `ingest_cohort` strips it to form each `subject_id`
  (e.g. `sub-verse004` from `sub-verse004_seg-vert_msk.nii.gz`).
- `--source` and `--build-date` are caller-supplied and stamped verbatim
  into `provenance` (never derived from `date.today()`), so re-running the
  same command on a different date reproduces identical provenance.
- With scans staged as `<id>_scan.nii.gz` siblings, the build carries all
  three feature families at once: geometry (item 044,
  `INGESTED_FEATURES`), intensity (item 063,
  `INGESTED_INTENSITY_FEATURES`), and morphology (item 081,
  `INGESTED_MORPHOLOGY_FEATURES` —
  `largest_component_fraction`, `component_count`, `eigenvalue_ratio`), at
  schema version `"1.2"`. `build_reference` defaults `with_morphology=True`
  and `with_intensity=True`, and `_handle_build_reference` does not
  override either flag, so no extra CLI switches are required to get the
  full `"1.2"` artifact.
- An absent or empty `--cohort` (or a mistyped `--seg-suffix` that matches
  nothing) errors cleanly: `segqc build-reference` exits non-zero, writes no
  partial file at `--out`, and prints an `Error:`-prefixed message to
  stderr — no Python traceback. This is existing behaviour
  (`_handle_build_reference` catching `(OSError, ReferenceArtifactError)`),
  exercised (not newly implemented) by this item's tests.

## Deployment selection

A deployment picks up the real-VerSe artifact instead of the bundled
default via either:

- the CLI flag: `segqc run --reference-artifact src/segqc/reference/reference_verse_v1.json …`, or
- the config key: `reference.artifact_path: src/segqc/reference/reference_verse_v1.json`
  in the run config.

**Discouraged alternative — bundle-swap.** Overwriting
`reference_default.json` in place with a real-VerSe build is explicitly
**not** recommended: it would destroy the reproducible synthetic baseline
that Stage 6/8 determinism tests assert against, and it collapses the
distinction between "test fixture" and "grounded reference" that this policy
exists to preserve. Always ship the real build under its own versioned
filename and select it explicitly.

## Reproducibility & automation

- `build_date` is always **caller-supplied**, never `date.today()` — the
  same invocation on any date produces identical `provenance.build_date`.
  This is what makes the build recipe deterministic and testable (see
  `tests/test_082_verse_build_recipe.py`'s AC2 assertion that a re-run with
  the same arguments reproduces the same stamped values).
- `eigenvalue_ratio` (item 081's PCA-based morphology feature) is a
  platform-sensitive float — its last few bits of precision can differ
  across BLAS/LAPACK implementations. Two builds of the *same* cohort should
  be compared with a numeric tolerance (`segqc.synth.golden.reports_close`),
  not byte-identity, per items 078/081.
- The real-VerSe artifact is **committed once**, by whoever runs the build
  against the mounted real cohort — it is **not** regenerated in CI (CI has
  no access to the real data, and even if it did, the eigenvalue-ratio float
  would make a byte-determinism test flaky across CI runners). No
  cross-platform byte-determinism test is run against it; only the bundled
  synthetic default carries that guarantee.
- For a **one-command** refresh (rebuild synthetic default + optionally the
  real artifact when a cohort is mounted + re-evaluate), see **item 083**'s
  refresh wrapper — this document only covers the manual invocation of the
  existing `segqc build-reference` CLI.
