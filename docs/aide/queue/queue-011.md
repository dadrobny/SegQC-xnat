# Seg-QC-xnat — Work Queue 011

> **Status:** Live · **Created:** 2026-07-16
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Opens **Stage 13**; supersedes the completed [`queue-010.md`](queue-010.md)
> (Stage 12, closed 2026-07-16).

---

## Scope of this queue

Delivers roadmap **Stage 13 — Dataset Ingestion Adapters & Harmonization
Schema** in full. Today ingestion
(`segqc.reference.ingest.ingest_cohort`) is **flat, non-recursive, and hardcodes
a `<id>_scan.nii.gz` sibling**, so a nested/varied real dataset — e.g. VerSe's
`derivatives/sub-verseNNN/…_seg-vert_msk.nii.gz` + `rawdata/…_ct.nii.gz` — can't
be read without manual copy/symlink staging (the item-082 recipe). This queue
introduces a **dataset-agnostic `Cohort`/`Case` interface** plus **declarative,
per-dataset adapters** that map arbitrary datasets onto it, and wires that path
into the CLI — removing the staging friction and unblocking the real-data half of
Stage 12 (building `reference_verse_vN` and evaluating held-out real GT through a
clean interface, rather than a throwaway staging hack).

**Why this exists (2026-07-16).** Verifying Stage 10 on real GPU hardware and
mounting real VerSe19 data (`/mnt/data/spine/data/datasets/VerSe/VerSe19/…`)
surfaced two facts: the dataset root differs from the documented layout (it
directly contains `derivatives/`+`rawdata/`, no double-nested wrapper) and file
naming drifts (`_seg-vb_ctd.json`). Hard-wiring one dataset's layout doesn't
scale to VerSe20, TotalSegmentator, or SPINEPS outputs — hence a schema.

**Design principle — the framework stays dataset-agnostic.** Its three
operations (`run` a case, `build-reference` from a GT cohort, `evaluate` a cohort
or a build+held-out pair) consume **only** a `Cohort`. Folder structure, naming,
label mapping, and *subset selection* live entirely in the adapter. A
train/val/test split is just **one kind of subset** (others: CSV / id-list /
glob); the framework must not expect pre-split datasets. This keeps clean the
separation between (1) code/function testing on synthetic fixtures, (2) building
a real-GT reference/heuristic knowledge base, and (3) applying the tool to score
new automatic segmentations.

**Prioritisation & sequencing.** **Interface + resolver first** (086) — pure,
data-access-independent, testable against tiny synthetic nested fixtures. Then
the integration + CLI surface (087) that routes ingestion/manifest-building
through it. Finally the committed VerSe19 descriptor + Stage-13 acceptance (088),
whose real-cohort validation is environment-gated (skips cleanly when the
uncommitted VerSe cohort is absent). Recommended order: **086 → 087 → 088**.

**Key constraint — real VerSe data is not committed.** Every item runs and is
tested against **synthetic nested fixtures**; item 088's real-cohort check is
gated on a mounted-cohort detector and **skips cleanly when absent** (mirroring
items 069/077–080/084). No raw scans are committed — only the small VerSe19
descriptor.

### Numbering note

Items 001–085 are complete or specced (Stages 0–12 ✅; Stage 10 GPU verification
hardening = item 085). This queue continues at the next free integer: **086–088**.

**Estimated size:** ~1 week (3 items, within `loop.queue_cap = 10`).

### Stage-13 deliverable → item coverage

| Stage-13 deliverable | Delivered by item |
|---|---|
| `Cohort`/`Case` interface + descriptor schema + resolver (`segqc.datasets`) | 086 |
| Cohort-driven ingestion/manifest path + CLI `--dataset-schema`/`--data-root`/`--subset` | 087 |
| Committed VerSe19 descriptor + Stage-13 acceptance (real-cohort check env-gated) | 088 |

---

## Work items

### Item 086: Dataset-agnostic `Cohort`/`Case` interface + descriptor schema + resolver
Add a new `segqc.datasets` module providing: the framework-facing data model —
`Case` (`case_id`, `seg_path`, `scan_path | None`, `role` ∈ {`gt`,`candidate`},
resolved `label_convention`, optional `metadata`) and `Cohort` (an ordered,
deterministic collection of `Case`s); a **declarative descriptor** loader
(YAML/JSON) with fields `data_root`, `seg` (recursive glob), `scan`
(template/glob or none), `case_id` (regex/template extraction incl.
split-subject infixes), `label_convention`, `role`, and optional named
`subsets` (folder / CSV / id-list / glob); and a **resolver**
`resolve(descriptor, *, data_root=None, subset=None, role=None) -> Cohort` that
walks the dataset per the descriptor and yields resolved `Case`s in a stable
order. Subset selection is adapter-only — the framework never sees it. *Testable:*
against tiny **synthetic nested fixtures** built in `tmp_path` (a
`derivatives/…`+`rawdata/…`-shaped tree and a flat tree), `resolve` returns the
expected `(case_id, seg_path, scan_path)` triples with deterministic ordering;
`subset=` selects the right cases via each mechanism (folder, CSV, id-list,
glob); a missing/None `scan` yields `scan_path=None` without raising; a bad
descriptor errors cleanly (no traceback). No real data.

### Item 087: Cohort-driven ingestion/manifest path + CLI schema flags
Thread the item-086 `Cohort` through the existing surfaces **without breaking the
flat path**: give `segqc.reference.ingest.ingest_cohort` (and item-084's
`build_gt_pass_manifest`) a `Cohort`-driven discovery mode alongside the current
flat `os.listdir` + hardcoded-`_scan.nii.gz` behaviour (retained for the
synthetic determinism fixtures), and add the CLI surface
`--dataset-schema <descriptor> [--data-root <dir>] [--subset <name|csv>]` to
`run`, `build-reference`, and `evaluate`, resolving a descriptor to a `Cohort`
that feeds the same downstream code. *Testable:* driving each subcommand
in-process (`segqc.cli.main`) with `--dataset-schema` over a synthetic **nested**
fixture produces the same well-formed output (reference artifact / eval report /
run report) as the equivalent flat cohort; omitting the flags leaves the flat
path byte-for-byte unchanged; `--subset` restricts the cohort; the pre-existing
ingestion/evaluate tests stay green.

### Item 088: Committed VerSe19 descriptor + Stage-13 acceptance *(completes Stage 13)*
Add a committed **VerSe19 descriptor** (e.g. `src/segqc/datasets/verse19.yaml`)
encoding the real layout (`derivatives/sub-verse*/…_seg-vert_msk.nii.gz` masks,
`rawdata/…_ct.nii.gz` scans, `sub-verseNNN[_split-verseMMM]` case ids, VerSe
label convention, `training`/`validation`/`test` as named `subsets`). Provide a
Stage-13 acceptance module that exercises the full `descriptor → resolve →
build-reference/evaluate` path over a **synthetic VerSe-shaped stand-in cohort**
in CI, and a **real-cohort clause gated** on a mounted-cohort detector (env var,
e.g. `SEGQC_VERSE_COHORT`) that resolves the *actual* mounted VerSe19 and asserts
the expected subject/scan/seg triples (incl. split subjects) — **skipping cleanly
when the cohort is absent** (mirroring items 069/084). Reconcile `progress.md`
(Stage 13 → done); `roadmap.md` is PR-gated and not edited by this direct-merge
item. *Testable:* the synthetic-stand-in path runs unconditionally (well-formed
artifact/report, deterministic resolution, split subsets handled); the
real-VerSe clause is a genuine `skipif` that skips on a data-absent host; a check
confirms no raw scans are committed (only the descriptor).

---

## Current state (2026-07-16)

Freshly generated after Stage 10 GPU verification (item 085) and the real-VerSe
data mount. This is the **Live** queue; it opens **Stage 13 — Dataset Ingestion
Adapters & Harmonization Schema** and supersedes the completed
[`queue-010.md`](queue-010.md). No Stage 13 items claimed yet. **086** (interface
+ resolver) is pure and data-independent — land it first; **087** (integration +
CLI) then routes ingestion through it; **088** (VerSe19 descriptor + acceptance)
closes the stage with its real-cohort check environment-gated. This queue lands
together with the Stage-13 roadmap/vision addition via a single human-reviewed PR
(roadmap is PR-gated).

## Next Step

Spec the whole queue now with `/aide-spec-queue 011` in one interactive sitting,
or spec per-item during execution via `/aide-run-queue 011`. Start with **086**
(interface + resolver — no dataset data needed).
