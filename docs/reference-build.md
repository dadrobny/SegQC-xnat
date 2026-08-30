# Reference-artifact build recipe

> Companion to [`docs/aide/dataset-verse19.md`](aide/dataset-verse19.md) (the
> real-VerSe layout/naming facts) and the item-082 spec
> ([`docs/aide/items/082-real-verse-build-recipe.md`](aide/items/082-real-verse-build-recipe.md)).
> This document is the **recipe + policy**; it adds no code. The build
> machinery it drives (`segfacet build-reference`, `ingest_cohort`,
> `build_reference`, `write_artifact`, `load_artifact`) already exists
> (items 044/045/063/081).

## Overview

The project ships and consumes **two** reference-data artifacts:

1. **The committed synthetic default** — `src/segfacet/reference/reference_default.json`.
   Built from a fixed, seeded, no-wall-clock synthetic cohort
   (`segfacet.reference.artifact.build_default_cohort`) via
   `python -m segfacet.reference.artifact`. This is the **test/determinism
   baseline**: it is byte-reproducible across platforms and runs, and Stage
   6/8 determinism tests depend on it never changing shape unexpectedly. It
   is not a stand-in for real anatomical grounding.
2. **A separately versioned real-VerSe artifact** —
   `reference_verse_vN.json` (e.g. `reference_verse_v1.json`), with
   `provenance.source == "verse-vN"` (e.g. `"verse-v1"`). Built from a real
   mounted VerSe ground-truth cohort via `segfacet build-reference` (see
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
  it is committed under `src/segfacet/reference/` as package data (so it ships
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

The dataset root's exact nesting depth beneath the configured cohort root is
not fixed (see `docs/aide/dataset-verse19.md`'s "Git / versioning policy" —
some extraction tools produce a wrapping `dataset-verse19training/` directory
around the actual root, some don't); either way it contains:

```
rawdata/sub-verseNNN/sub-verseNNN_ct.nii.gz
derivatives/sub-verseNNN/sub-verseNNN_seg-vert_msk.nii.gz
```

(plus split-subject `_split-verseMMM` infixes, centroid JSON, and preview
PNGs that the build recipe does not need).

## Staging the cohort for ingestion

`segfacet.reference.ingest.ingest_cohort` was built for item 044's flat,
**non-recursive** convention: it lists a single `--cohort` directory with
`os.listdir` (no recursive walk of subdirectories) looking for files ending
in `--seg-suffix`, and for each match hardcodes the sibling scan filename as
`<id>_scan.nii.gz` (there is no `--scan-suffix` flag). Real VerSe's on-disk
layout does not match this directly — masks live nested under
`derivatives/sub-verseNNN/`, and CT scans are named `..._ct.nii.gz`, not
`..._scan.nii.gz`.

**Item 123 ships the reproducible path**: `scripts/rebuild_verse_reference.py`
resolves the cohort root (`--verse-cohort`, else the `SEGFACET_VERSE_COHORT`
environment variable), discovers masks by a **recursive** glob for
`*_seg-vert_msk.nii.gz` beneath that root (so either nesting layout works with
no flag), stages a flat directory of symlinks (falling back to copies) that
satisfies `ingest_cohort`'s convention — each mask under its own filename plus
a `<subject_id>_scan.nii.gz` sibling for every mask whose CT was found — and
then drives `build_reference` / `write_artifact` over the staged directory
itself:

```bash
.venv/bin/python scripts/rebuild_verse_reference.py \
    --out out/verse-rebuild \
    --verse-cohort "$SEGFACET_VERSE_COHORT" \
    --build-date 2026-08-29
```

(`--verse-cohort` may be omitted once `SEGFACET_VERSE_COHORT` is exported;
the CLI flag overrides the environment variable when both are given.) The
tool never writes beneath the cohort root, and never writes the committed
package copy under `src/segfacet/` — it writes
`<out>/reference_verse_v1.json` and a structured
`<out>/verse_rebuild_summary.json` recording the discovered cohort, the
staging outcome, the built artifact's identity, and the derived
`mislabel.max_offset_mm` calibration (see AC9–AC17 in
[`docs/aide/items/123-recalibrate-and-regenerate-downstream-artifacts.md`](aide/items/123-recalibrate-and-regenerate-downstream-artifacts.md)).
Installing the rebuilt artifact — copying `<out>/reference_verse_v1.json`
over `src/segfacet/reference/reference_verse_v1.json` — remains a separate,
explicit operator step, exactly as it does for `scripts/refresh_reference.py`.

An unreachable cohort (no root resolvable, or a root with no matching masks)
is a structured skip recorded in the summary's `cohort` block, never a
traceback: `main` still returns `0`.

## Build invocation (manual alternative)

The staging tool above is the reproducible path for a real VerSe cohort; the
underlying `segfacet build-reference` CLI can still be driven directly
against an already-flat staged directory when that's more convenient:

```bash
segfacet build-reference \
    --cohort staged_verse \
    --out src/segfacet/reference/reference_verse_v1.json \
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
  nothing) errors cleanly: `segfacet build-reference` exits non-zero, writes no
  partial file at `--out`, and prints an `Error:`-prefixed message to
  stderr — no Python traceback. This is existing behaviour
  (`_handle_build_reference` catching `(OSError, ReferenceArtifactError)`),
  exercised (not newly implemented) by this item's tests.

## Deployment selection

A deployment picks up the real-VerSe artifact instead of the bundled
default via either:

- the CLI flag: `segfacet run --reference-artifact src/segfacet/reference/reference_verse_v1.json …`, or
- the config key: `reference.artifact_path: src/segfacet/reference/reference_verse_v1.json`
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
  be compared with a numeric tolerance (`segfacet.synth.golden.reports_close`),
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
  existing `segfacet build-reference` CLI.

## Rebuild record — 2026-08-29 (item 123)

`scripts/rebuild_verse_reference.py` was run against the full, real 80-subject
VerSe19 training cohort (`SEGFACET_VERSE_COHORT`, no CT/mask missing). The
build completed cleanly — all 25 canonical levels present, `subject_count ==
80` — and `derive_max_offset_mm` (item 123's pure `mislabel.max_offset_mm`
derivation rule, `p99`-over-qualifying-levels rounded up to the next `0.5`
mm, floored at `6.0` mm) measured the real-GT ceiling `P = 21.209073949050172`
mm at level `L5` (`count = 62`), giving a derived threshold of `21.5` mm.

**That value falls outside the corpus window `(5.143859, 17.507445]`** that
the 2026-08-27 "Spinal curve model — the deformity envelope" human gate
(`progress.md`, `## Human gates`) approved, so the recalibration was **not**
applied: `heuristics/mislabel.py`'s `_DEFAULT_MAX_OFFSET_MM` stays `15.0`,
and `reference_verse_v1.json` / `reference_default.json` / the corpus
goldens are unchanged. This is the item's own spec-mandated hand-back
outcome (see the item's Decisions log), not a build failure — the real GT
does reach into and past the approved envelope at `L5`, and widening (or
otherwise revising) that envelope needs a person's decision, not a rebuild.
The full evidence (`p99_by_level`, the qualifying-level list, and the
top-offset subject ids) is in the rebuild's own
`verse_rebuild_summary.json`, regenerable by re-running the command above.

## Rebuild record — 2026-08-29, resolved (item 123, terminal-vertebra exclusion)

A follow-up per-vertebra analysis of the 2026-08-29 measurement above showed
the `L5` anomaly was entirely a **terminal-extrapolation** artefact of item
120's held-out estimator (terminal `L5` `p99` `21.5` mm vs. interior `L5`
maximum `1.00` mm across the same 80-subject cohort), not real deformity. By
human decision the same date, sequence-terminal vertebrae (a subject's
cranial-most and caudal-most present level) are excluded from both the
`mislabel` rule and the reference distribution
(`src/segfacet/features/spline_offset.py`'s `is_terminal` flag;
`reference/ingest.py` / `reference/delta.py` exclude it symmetrically; see
the item spec's Decisions log for the full record).

`scripts/rebuild_verse_reference.py` was re-run against the same 80-subject
cohort (reusing the cached staged directory) under this exclusion. The
interior-only ceiling `P = 12.90577608928562` mm at level `T10`
(`count = 37`) derives a threshold of **`13.0` mm** — inside the approved
corpus window `(5.143859, 17.507445]` — so the recalibration is applied:
`heuristics/mislabel.py`'s `_DEFAULT_MAX_OFFSET_MM` and
`default_config.yaml`'s `rules.mislabel.max_offset_mm` are both `13.0`;
`reference_verse_v1.json` and `reference_default.json` are rebuilt (the
latter via `python -m segfacet.reference.artifact`); the nine corpus goldens
and `tests/golden/022_stage3_report.json` are regenerated to carry
`is_terminal`, with `mode1_displace` and `mode6_crop_at_border` additionally
moving their `mislabel` finding's threshold clause from `15.0` to `13.0` mm.
`L5` dropped to 3 interior occurrences (below the `count >= 10` qualifying
floor, mean `0.69` mm) and `C1` (always terminal-only in this cohort) carries
no `spline_offset_mm` statistic at all — both expected consequences of the
exclusion. `spline_offset_mm` is therefore now an **interior-only** feature
end to end. Full evidence (`terminal_count`/`interior_count`, `p99_by_level`,
the qualifying-level list, and the top-offset subject ids) is in the
re-run's `verse_rebuild_summary.json`.

**Intensity coverage changed with this rebuild.** The pre-123 (2026-07-17)
committed `reference_verse_v1.json` computed every level's `intensity_*`
statistics from a strict *subset* of that level's subjects (e.g. `L1`: 47 of
59; `C1`–`C4`: 1 of 13) — most likely because the manual staging recipe this
document used to carry iterated over each split-subject's *parent* directory
and so could never name a split subject's own `${sub}_split-verseMMM_ct.nii.gz`
CT. Item 123's rebuild tool discovers CTs recursively and split-infix-aware,
finds one for all 80 subjects, and the rebuilt artifact's intensity coverage is
complete (`count == record_count` on every level). Verified not to be a
scan/mask mispairing: zero geometric features moved on any level, and
spot-checked HU ranges are physiologically plausible. Anything measuring or
re-deriving thresholds from `reference_verse_v1.json`'s `intensity_*`
statistics (e.g. `heuristics/intensity_reference_delta.py` defaults) should
know a pre-123 baseline undercounted every level.
