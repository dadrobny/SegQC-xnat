# Item 083 — One-command reference-refresh wrapper (graceful without VerSe data)

> **Created:** 2026-07-15 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7)
> **Queue:** [`../queue/queue-010.md`](../queue/queue-010.md) · Item 083 *(third Stage-12 item; automates the 081/082 recipe — degrades gracefully when the uncommitted real-VerSe cohort is absent)*
> **Objectives:** G3 (reference-grounded — one command to refresh every reference
> artifact and re-evaluate, so "we added a feature / changed config → refresh
> everything" is a single, CI-usable step) and G7 (evaluable & reproducible — the
> wrapper is deterministic, self-contained, and writes only into a caller-supplied
> output dir).
> **Suggested branch:** `aide/083-reference-refresh-wrapper` *(batch-specced on `aide/specs-queue-010`; execution branch created at claim time)*

---

## Description

Add a single, re-runnable **project tool** — `scripts/refresh_reference.py` — that,
in one invocation, refreshes the project's reference artifacts and re-runs the
Stage-7 evaluation so a maintainer who changed a feature or config can rebuild
and re-check *everything* with one command (usable in CI).

In one `main(argv)` invocation it:

1. **Rebuilds the synthetic default reference artifact** — via item 045's
   `build_and_write_default(<out>/reference_default.json)`, writing a fresh
   `reference_default.json` **into the caller's `--out` dir** (never touching the
   committed package copy).
2. **Synthesizes a tiny, deterministic evaluation cohort from the production synth
   builders** — a couple of clean spines from
   `segqc.synth.clean_gt.build_clean_spine` used as **self-vs-self** cases
   (candidate == GT → expected `pass`), written into `--out` as GT/candidate
   NIfTIs plus an `evaluate`-shape manifest (`{"manifest_version": 1, "cases":
   [{"case_id", "gt", "candidate", "expected": {"expected_verdict": "pass"}}]}`).
   No `tests/corpus/` fixtures and no `scripts/`→`tests/` coupling — it works in a
   deployed checkout, and the false-positive rate is well-defined (expected-pass
   negatives are present).
3. **Runs `segqc evaluate` over that cohort** — through `segqc.cli.main(["evaluate",
   …])` — producing a well-formed `<out>/…/eval_report.json` carrying an FPR
   metric.
4. **Optionally builds the versioned real-VerSe artifact** — **only if**
   `--verse-cohort <dir>` is supplied *and* the directory exists — via item 045's
   `build_reference(...)` following item 082's recipe (`source="verse-…"`,
   `seg_suffix` = the real VerSe mask suffix), writing a separate
   `reference_verse_*.json` into `--out`. When `--verse-cohort` is absent or points
   at a nonexistent path, **all real-VerSe steps skip cleanly** — a structured
   skip with an explicit reason, never a failure, and the synthetic path still
   completes with exit 0.

Every step's outcome is reported in a **machine-checkable structured summary**: a
`dict` returned from the orchestration helper *and* written to
`<out>/refresh_summary.json`, with a per-step `name` / `status`
(`ran`/`skipped`/`failed`) / `reason`, so a test can assert the real-VerSe step is
a **genuine** skip (an explicit `status == "skipped"` entry with a reason), not a
silent no-op — mirroring the genuine-skip proofs of items 069/077–080.

### What it is — precise scope

- **A project tool at `scripts/refresh_reference.py`**, loaded by path, with a
  testable `main(argv) -> int` plus **pure helpers** (a cohort-synthesis helper and
  an orchestration helper returning the summary `dict`) — exactly the shape of
  `scripts/aide_status_report.py`. **NOT** a new `segqc` CLI subcommand.
- **Self-contained synthesis:** the evaluation cohort is generated at runtime from
  the production synth builders (`build_clean_spine`, optionally
  `paint_clean_scan`), the same builders `build_default_cohort` already uses — so
  there is no dependency on `tests/corpus/**` or the `tests` package.
- **Graceful, structured degradation** of the real-VerSe steps when the
  (uncommitted, large/licensed) VerSe cohort is absent.

### What it is NOT — fenced scope

- **NOT a change to `segqc`'s production package.** This item adds only
  `scripts/refresh_reference.py` and its test; it does **not** add a CLI
  subcommand, edit `src/segqc/**`, or add package data. It *drives* the existing
  `build_and_write_default` / `build_reference` / `segqc evaluate` surfaces.
- **NOT the real-VerSe evaluation / verification-table closure.** Quantifying the
  G3 false-positive rate on **real** VerSe GT and flipping the "Real VerSe GT" row
  in `progress.md`'s Environment-Gated Capability Verification table to
  ✅ Verified is **item 084**. This item exercises the evaluate *path* over the
  self-synthesized cohort and (when a stand-in verse cohort is supplied) the
  versioned *build* path; it does not add or flip that row, and does not commit a
  real `reference_verse_vN.json`.
- **NOT the recipe document.** `docs/reference-build.md` (storage/versioning/
  acquisition policy) is item 082's deliverable; this wrapper automates the build
  invocation that document describes.
- **NOT a widening of ingestion/aggregation/schema.** Those are item 081's; this
  wrapper consumes 081/082's realised interfaces.

---

## Public interface (the surface this item adds)

```python
# scripts/refresh_reference.py  (a path-loaded project tool, not part of the segqc package)

#: Canonical per-step names used in the summary (stable identifiers a test asserts on).
STEP_SYNTH_REBUILD  = "synthetic-default-rebuild"
STEP_EVAL_COHORT    = "synthetic-eval-cohort"
STEP_SYNTH_EVALUATE = "synthetic-evaluate"
STEP_VERSE_BUILD    = "verse-build"
STEP_VERSE_EVALUATE = "verse-evaluate"

#: Default real-VerSe mask suffix (item 082 recipe) used when a --verse-cohort is supplied.
DEFAULT_VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"

def synthesize_eval_cohort(out_dir, *, spec=None) -> "pathlib.Path":
    """Write a deterministic self-vs-self clean-spine eval cohort (GT + candidate
    NIfTIs + an `evaluate`-shape manifest) into *out_dir* from
    `segqc.synth.clean_gt.build_clean_spine`. Returns the manifest path. No RNG
    beyond the seeded synth builders; reads no wall clock."""

def run_refresh(out_dir, *, verse_cohort=None,
                verse_seg_suffix=DEFAULT_VERSE_SEG_SUFFIX,
                build_date="2026-07-15") -> dict:
    """Orchestrate the refresh; write only under *out_dir*; return the summary dict
    (see shape below). Never raises for an absent/missing verse cohort — that path
    is a structured skip."""

def main(argv=None) -> int:
    """Parse argv (`--out <dir>` required; `--verse-cohort <dir>`,
    `--verse-seg-suffix`, `--build-date` optional), call `run_refresh`, write
    `<out>/refresh_summary.json`, and return a process exit code (0 = the
    synthetic path completed; the verse skip does not change that)."""
```

**Summary dict shape** (also serialised to `<out>/refresh_summary.json`):

```jsonc
{
  "out_dir": "<abs path>",
  "verse_cohort": null,                 // or the supplied path
  "steps": [
    {"name": "synthetic-default-rebuild", "status": "ran",     "reason": "...", "output": "<out>/reference_default.json"},
    {"name": "synthetic-eval-cohort",     "status": "ran",     "reason": "...", "output": "<out>/eval_cohort/manifest.json"},
    {"name": "synthetic-evaluate",        "status": "ran",     "reason": "...", "output": "<out>/eval_synthetic/eval_report.json"},
    {"name": "verse-build",               "status": "skipped", "reason": "no --verse-cohort supplied", "output": null},
    {"name": "verse-evaluate",            "status": "skipped", "reason": "no --verse-cohort supplied", "output": null}
  ]
}
```

`status ∈ {"ran", "skipped", "failed"}`; every `skipped`/`failed` entry carries a
**non-empty** `reason`.

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. The wrapper is loaded by
path (like `scripts/aide_status_report.py`) and driven via `main(argv)` /
`run_refresh(...)` into a `tmp_path` output dir. "The committed default artifact"
is `segqc.reference.default_artifact_path()`. "Well-formed artifact" means
`segqc.reference.load_artifact` parses it into a `ReferenceDistribution` without
raising._

### A. Wrapper presence & shape

- [ ] **AC1: The wrapper exists with a callable `main(argv)`.**
      `scripts/refresh_reference.py` exists and, when loaded by path, exposes a
      `main` callable that accepts an `argv` list and returns an `int` exit code.

### B. Synthetic refresh path (no `--verse-cohort`)

- [ ] **AC2: A no-`--verse-cohort` invocation exits 0.** `main(["--out",
      str(tmp_out)])` returns `0`.

- [ ] **AC3: It rebuilds the synthetic default reference artifact into `--out`.**
      After the AC2 invocation a well-formed reference artifact exists at
      `<out>/reference_default.json` (parsed by `load_artifact` into a
      `ReferenceDistribution` with a non-empty `schema_version` and at least one
      per-level `feature_stats` entry).

- [ ] **AC4: It synthesizes a deterministic self-vs-self eval cohort from
      `build_clean_spine`.** The invocation writes, under `--out`, an
      `evaluate`-shape manifest (`{"manifest_version": 1, "cases": [...]}`) plus the
      referenced GT and candidate NIfTIs, with **at least one** case whose
      `candidate` file bytes equal its `gt` file bytes (self-vs-self) and whose
      `expected.expected_verdict == "pass"`; every `gt`/`candidate` path in the
      manifest resolves to an existing file.

- [ ] **AC5: It runs `segqc evaluate` producing a well-formed `eval_report.json`
      with an FPR metric.** A `eval_report.json` is written under `--out`, parses as
      JSON, carries a `schema_version` and a `metrics` block, and
      `metrics["false_positive_rate"]` is present and a float in the inclusive
      range `[0.0, 1.0]` (for the self-vs-self clean cohort the expected value is
      `0.0`).

- [ ] **AC6: It emits a machine-checkable structured summary.**
      `<out>/refresh_summary.json` is written **and** `run_refresh(...)` returns a
      `dict` with a `steps` list; every step entry is a mapping with a `name`, a
      `status` in `{"ran", "skipped", "failed"}`, and a `reason` string; the two
      objects (returned dict and the written JSON) carry the same per-step
      `name`/`status`.

### C. Genuine skip of the real-VerSe steps

- [ ] **AC7: With no `--verse-cohort`, the real-VerSe build step is a GENUINE
      skip.** In the AC2 summary the `verse-build` step is present with
      `status == "skipped"` and a **non-empty** `reason` that names the absent
      `--verse-cohort` (it is not missing from the list and its status is not
      `"ran"`) — the skip is asserted structurally, not as a silent no-op.

- [ ] **AC8: The skip does not abort the synthetic path.** In the same run the
      three synthetic steps (`synthetic-default-rebuild`, `synthetic-eval-cohort`,
      `synthetic-evaluate`) all have `status == "ran"` and `main` returns `0` — the
      real-VerSe skip completes the run, it does not fail it.

- [ ] **AC9: A nonexistent `--verse-cohort` path is treated as absent, not a
      crash.** `main(["--out", str(tmp_out), "--verse-cohort", <nonexistent-dir>])`
      returns `0`, the `verse-build` step is `status == "skipped"` with a reason
      naming the missing path, and the combined captured output contains **no**
      Python traceback (`Traceback (most recent call last)`).

### D. Real-VerSe build path (stand-in cohort supplied)

- [ ] **AC10: With a present `--verse-cohort`, the real-VerSe build step runs and
      produces a versioned artifact.** Given a tiny synthetic VerSe-shaped stand-in
      cohort (built from `build_clean_spine` + `paint_clean_scan` as
      `<id>_seg-vert_msk.nii.gz` + `<id>_scan.nii.gz` pairs) at `--verse-cohort`,
      the `verse-build` step has `status == "ran"`, a `reference_verse_*.json` is
      written under `--out`, and `load_artifact` parses it into a
      `ReferenceDistribution` whose `provenance.source` starts with `"verse-"`.

### E. Determinism, containment, self-containment

- [ ] **AC11: The wrapper is deterministic.** Two no-`--verse-cohort`
      invocations into two separate `--out` dirs produce (a) equal per-step
      `name`/`status` sequences in `refresh_summary.json`, (b) **byte-identical**
      `reference_default.json` (intra-platform), and (c) equal parsed eval-cohort
      manifests (identical `case_id`s and `expected` blocks).

- [ ] **AC12: The wrapper writes only into `--out`.** After a full invocation the
      committed `default_artifact_path()` file is **byte-unchanged** and every file
      created or modified by the run lies inside the caller-supplied `--out` dir
      (nothing is written under `src/segqc/**` or elsewhere in the tree).

- [ ] **AC13: No dependency on `tests/corpus/` or the `tests` package.** A source
      scan of `scripts/refresh_reference.py` finds **no** reference to
      `tests/corpus` and **no** import of the `tests` package — the evaluation
      cohort is synthesized solely from `segqc.synth` / `segqc.reference`
      production builders, so the wrapper runs in a deployed checkout with no test
      fixtures present.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume`; the ambiguous queue one-liner was resolved by **three
confirmed human decisions** (below). Remaining defaults, and the upstream
interfaces this spec pins ahead of 081/082 merging, are recorded for audit — the
builder/validator **hand back if reality diverged**.

- **Confirmed decision Q1 (evaluation target = self-contained synthesis from
  production builders).** The wrapper generates its own tiny deterministic
  evaluation cohort at runtime from `segqc.synth.clean_gt.build_clean_spine` (as
  `build_default_cohort` already does): a couple of clean spines as
  **GT == candidate** (self-vs-self → expected `pass`), written as GT/candidate
  NIfTIs plus an `evaluate`-shape manifest into `--out`, then evaluated via `segqc
  evaluate`. **No `scripts/`→`tests/` coupling and no dependency on
  `tests/corpus/`** — it works in a deployed checkout, and FPR is well-defined
  (expected-pass negatives are present, so `fp + tn > 0`).

- **Confirmed decision Q2 (location / shape = `scripts/refresh_reference.py`).** A
  project tool loaded by path with a testable `main(argv)` plus pure helpers
  (exactly like `scripts/aide_status_report.py`), **NOT** a new `segqc` CLI
  subcommand. Rerun via `python scripts/refresh_reference.py --out <dir>
  [--verse-cohort <dir>]`.

- **Confirmed decision Q3 (run summary = machine-checkable structured summary).**
  The wrapper emits a `dict` (returned from `run_refresh`) **plus** a
  `refresh_summary.json` written into `--out`, with a per-step `ran`/`skipped`/
  `failed` status + reason, so a test asserts the real-VerSe step is a **genuine**
  skip (`status == "skipped"`, explicit reason) when no `--verse-cohort` is given,
  not a silent no-op — mirroring items 069/077's genuine-skip proofs.

- **The evaluate CLI is driven in-process via `segqc.cli.main(["evaluate", …])`**
  (not a subprocess), so the test exercises the real, documented CLI surface and
  its exit code without spawning a process. `segqc evaluate` writes
  `<out-arg>/eval_report.json` + `eval_report.txt`; the wrapper points its `--out`
  at a subdirectory of the caller's `--out` (e.g. `<out>/eval_synthetic/`).

- **Determinism knobs are pinned:** a fixed `build_date` default (`"2026-07-15"`,
  not `date.today()`), the seeded synth builders (`build_clean_spine`,
  `paint_clean_scan(seed=0)`), and item 045's caller-dated `build_and_write_default`
  / `build_reference` (which read no wall clock). Intra-platform two-run
  byte-identity therefore holds for `reference_default.json` even though its
  item-081 `eigenvalue_ratio` is a platform-sensitive PCA float (cross-platform
  identity is out of scope here — that is item 078's tolerance concern).

- **Real VerSe is not committed → the "cohort present" path (AC10) is tested with
  a tiny synthetic VerSe-shaped stand-in cohort** built from the production synth
  builders (`build_clean_spine` multi-level L1–L5 so Stage 3 runs, +
  `paint_clean_scan` siblings), written with the real VerSe mask suffix
  `_seg-vert_msk.nii.gz` (item 082's stand-in convention). No real, large, or
  licensed data is downloaded or committed, and **no** `reference_verse_*.json` is
  committed by this item.

- **Real-VerSe *evaluation* (quantified G3 FPR) and the verification-table closure
  are item 084, not this item.** The `verse-evaluate` step in the summary, when a
  verse cohort is supplied, re-runs `segqc evaluate` over a self-vs-self cohort
  synthesized from the stand-in verse GT (exercising the evaluate *path* over the
  available cohort, per queue clause (c)); it does **not** quantify a real-VerSe
  FPR nor flip any `progress.md` verification row. When `--verse-cohort` is absent,
  `verse-evaluate` is a genuine skip alongside `verse-build`.

- **Pinned upstream interface — item 081 (specced, NOT yet merged; hand back if the
  realised shape diverged):** `segqc.reference.schema.SCHEMA_VERSION == "1.2"` with
  `build_reference` defaulting `with_morphology=True` (and `with_intensity=True`),
  so `build_and_write_default` / `build_reference` auto-produce a `"1.2"` artifact
  carrying geometry + intensity + morphology with **no** flag override needed by
  this wrapper. If 081 gated morphology behind an explicit flag or a different
  schema string, AC3/AC10's artifacts still parse (this item asserts only
  well-formedness + provenance, not the family set), but the builder should hand
  back so the pin can be re-checked.

- **Pinned upstream interface — item 082 (specced, NOT yet merged; hand back if
  diverged):** the versioned real-VerSe build is `build_reference(cohort_dir,
  source="verse-…", build_date=…, seg_suffix="_seg-vert_msk.nii.gz")` producing an
  artifact with `provenance.source == "verse-…"` — a **separate** versioned file,
  never a replacement of the committed synthetic default. This wrapper follows
  that recipe; if 082 changed the source-label convention or the invocation, AC10
  fails loudly and the builder hands back.

- **Pinned upstream interfaces (merged ✅):**
  - **Item 045** — `build_and_write_default(dest_json)` (writes a fresh synthetic
    default artifact to an explicit path, defaulting to the committed one when
    `None`), `build_reference(cohort_dir, *, source, build_date, seg_suffix=…)`,
    `default_artifact_path()`, `load_artifact`; all read no wall clock.
  - **Item 057** — the `segqc evaluate` subcommand (`--cohort <manifest.json>
    --out <dir> [--cohort-id] [--build-date]`) → `evaluate_cohort` →
    `compute_cohort_metrics`, writing `<out>/eval_report.json` whose
    `metrics.false_positive_rate` is `CohortMetrics.to_dict()`'s FPR; and the
    `segqc.eval.cohort` manifest shape (`manifest_version`, `cases[].case_id/.gt/
    .candidate/.expected.expected_verdict`; paths resolved relative to the manifest
    file's own directory).
  - **Item 036** — `segqc.synth.clean_gt.build_clean_spine(*, levels, spacing,
    curve_amplitude_mm, convention)` returning a `CleanSpine` with a `.seg_img`
    `nib.Nifti1Image`.
  - **Item 058** — `segqc.synth.intensity.paint_clean_scan(seg_img, *, seed=0,
    model=DEFAULT_HU_MODEL)` for the stand-in verse cohort's sibling scans.
  - **`scripts/aide_status_report.py`** — the path-loaded project-tool pattern
    (module-level `REPO_ROOT`, `main(argv)`, pure helpers) this wrapper mirrors.

- **Self-contained, no `tests/` coupling.** The wrapper imports only production
  `segqc.*` modules; it never imports the `tests` package nor reads
  `tests/corpus/**`. The stand-in verse cohort used to exercise AC10 is built by
  the **test**, not the wrapper.

## Implementation Steps

Intended path: a **single new file** `scripts/refresh_reference.py`. **No** change
to `src/segqc/**`, no new CLI subcommand, no committed artifact.

1. **Module skeleton** (mirror `scripts/aide_status_report.py`): shebang, module
   docstring (purpose + `Usage::` block), `from __future__ import annotations`,
   stdlib imports (`argparse`, `json`, `pathlib`, `sys`), and
   `REPO_ROOT = Path(__file__).resolve().parents[1]`. Define the `STEP_*` name
   constants and `DEFAULT_VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"`.

2. **`synthesize_eval_cohort(out_dir, *, spec=None) -> Path`:** build a couple of
   clean spines via `segqc.synth.clean_gt.build_clean_spine` (fixed levels/spacing/
   curve params for determinism), save each as a GT NIfTI and a **byte-identical**
   candidate NIfTI (self-vs-self) under `<out_dir>/eval_cohort/`, and write a
   `manifest.json` there of shape `{"manifest_version": 1, "cases": [{"case_id":
   …, "gt": "<rel>", "candidate": "<rel>", "expected": {"expected_verdict":
   "pass"}}, …]}` with `gt`/`candidate` **relative to the manifest's own dir**
   (item 057 resolves them that way). Return the manifest path. Reads no wall
   clock; no RNG beyond the seeded builders.

3. **`run_refresh(out_dir, *, verse_cohort=None, verse_seg_suffix=…,
   build_date="2026-07-15") -> dict`:** create `out_dir`; run the steps, appending
   a `{"name","status","reason","output"}` entry per step to a `steps` list:
   - **synthetic-default-rebuild** — `build_and_write_default(out_dir /
     "reference_default.json")`; `status="ran"`.
   - **synthetic-eval-cohort** — `synthesize_eval_cohort(out_dir)`; `status="ran"`.
   - **synthetic-evaluate** — `segqc.cli.main(["evaluate", "--cohort",
     str(manifest), "--out", str(out_dir / "eval_synthetic"), "--build-date",
     build_date, "--cohort-id", "refresh-synthetic"])`; `status="ran"` (record the
     `eval_report.json` path).
   - **verse-build** / **verse-evaluate** — if `verse_cohort` is `None` or the path
     does not exist: append both as `status="skipped"` with an explicit `reason`
     (naming the absent/missing `--verse-cohort`). Otherwise: `build_reference(
     verse_cohort, source="verse-refresh-v1", build_date=build_date,
     seg_suffix=verse_seg_suffix)` → `write_artifact(dist, out_dir /
     "reference_verse_v1.json")` (`verse-build` `status="ran"`), then synthesize a
     self-vs-self eval cohort from the verse GT and `segqc evaluate` it into
     `<out>/eval_verse/` (`verse-evaluate` `status="ran"`).
   Return `{"out_dir": str(out_dir), "verse_cohort": … , "steps": steps}`. **Never
   raise for an absent/missing verse cohort** — that is a structured skip.

4. **`main(argv=None) -> int`:** `argparse` with `--out` (required), `--verse-cohort`
   (optional), `--verse-seg-suffix` (default `DEFAULT_VERSE_SEG_SUFFIX`),
   `--build-date` (default `"2026-07-15"`). Call `run_refresh(...)`, write the
   returned dict to `<out>/refresh_summary.json` (`json.dump(..., indent=2,
   sort_keys=True)` + trailing newline), print a one-line summary, and return `0`
   when the three synthetic steps ran (the verse skip does not change the exit
   code). Guard with `if __name__ == "__main__": raise SystemExit(main())`.

5. **Keep it self-contained:** import only `segqc.*` production modules; never
   import `tests` or read `tests/corpus/**`.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_083_refresh_reference.py`. Load
  the wrapper **by path** (via `importlib.util.spec_from_file_location`, as
  `tests/test_aide_status_report.py` loads `scripts/aide_status_report.py`) so the
  script's `main`/helpers are importable without a console entry point.
- **Helpers:** a `_load_wrapper()` module loader; a `_read_summary(out)` reader; a
  `_build_standin_verse_cohort(dir)` fixture that writes a tiny 2-subject
  VerSe-shaped cohort (`build_clean_spine` L1–L5 + `paint_clean_scan`, saved as
  `<id>_seg-vert_msk.nii.gz` + `<id>_scan.nii.gz` pairs) — built in the **test**,
  never by the wrapper.
- **Group A — presence/shape (AC1):** load the module, assert `callable(main)` and
  that `main([...])` returns an `int`.
- **Group B — synthetic path (AC2–AC6):** drive `main(["--out", str(tmp_path/"a")])`
  → assert exit 0 (AC2); `load_artifact(<out>/reference_default.json)` well-formed
  (AC3); parse the eval manifest, assert `manifest_version == 1`, ≥1 self-vs-self
  case with `gt` bytes == `candidate` bytes and `expected.expected_verdict ==
  "pass"`, and every referenced path exists (AC4); parse `eval_report.json`, assert
  `metrics["false_positive_rate"]` is a float in `[0.0, 1.0]` (and `== 0.0` for
  this clean self-vs-self cohort) (AC5); assert `refresh_summary.json` exists and
  the `run_refresh` return dict has the per-step `name`/`status`/`reason` shape
  matching the file (AC6).
- **Group C — genuine skip (AC7–AC9):** in the AC2 summary assert the `verse-build`
  step is present, `status == "skipped"`, non-empty `reason` naming
  `--verse-cohort` (AC7); assert the three synthetic steps are `status == "ran"`
  and exit was 0 (AC8); drive `main([..., "--verse-cohort", str(tmp_path/"nope")])`
  (nonexistent) → exit 0, `verse-build` skipped with a reason naming the missing
  path, and capture stdout+stderr to assert no `Traceback (most recent call last)`
  (AC9).
- **Group D — verse build (AC10):** build a stand-in verse cohort, drive
  `main([..., "--verse-cohort", str(standin)])` → `verse-build` step
  `status == "ran"`, a `reference_verse_*.json` exists under `--out`, and
  `load_artifact` parses it with `provenance.source` starting `"verse-"`.
- **Group E — determinism/containment/self-containment (AC11–AC13):** two runs into
  separate out dirs → equal step `name`/`status` sequences, byte-identical
  `reference_default.json`, equal parsed manifests (AC11); snapshot
  `default_artifact_path().read_bytes()` before/after a run and assert unchanged,
  and assert every path touched by the run is under `--out` (AC12); read
  `scripts/refresh_reference.py` source text and assert it contains no
  `"tests/corpus"` substring and no `import tests` / `from tests` (AC13).
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty-but-present `--verse-cohort`** (dir exists, no `*_seg-vert_msk.nii.gz`):
    the wrapper does not crash — `verse-build` is either a clean `failed` entry
    with a reason or a `ran` empty-distribution artifact (assert whichever the
    machinery does, and that the overall run still exits 0 and leaks no traceback).
  - **`--out` under a not-yet-existing parent:** the wrapper creates it (parents
    included) and still writes all outputs there.
  - **Idempotent re-run into the same `--out`:** a second `main` over an existing
    populated `--out` overwrites cleanly and yields an equal summary.
  - **Manifest paths are relative:** assert the written manifest stores `gt`/
    `candidate` as paths relative to the manifest's own dir (so the cohort is
    relocatable), matching item 057's resolution rule.

## Dependencies

- **Item 081 (🚧 specced ahead in this batch; must be built + merged for the
  refreshed artifacts to carry schema `"1.2"` + the morphology family):** pinned in
  Assumptions — AC3/AC10 assert only well-formedness/provenance, so they survive a
  minor 081 divergence, but the builder hands back if the pinned schema/flag
  contract changed.
- **Item 082 (🚧 specced ahead in this batch; the versioned real-VerSe build recipe
  this wrapper automates):** the `build_reference(..., source="verse-…",
  seg_suffix="_seg-vert_msk.nii.gz")` invocation and the separate-versioned-file
  policy. AC10 fails loudly (builder hands back) if 082's realised recipe diverged.
- **Item 045 (✅):** `build_and_write_default(dest_json)`, `build_reference`,
  `write_artifact`, `default_artifact_path`, `load_artifact` — the build/IO surface
  driven for the synthetic and verse artifacts.
- **Item 057 (✅):** the `segqc evaluate` subcommand + `evaluate_cohort` +
  `compute_cohort_metrics` and the `segqc.eval.cohort` manifest shape /
  relative-path resolution — the evaluation surface and the FPR metric asserted in
  AC5.
- **Item 036 (✅):** `segqc.synth.clean_gt.build_clean_spine` — the production
  builder the self-vs-self eval cohort is synthesized from (no `tests/corpus`
  coupling).
- **Item 058 (✅):** `segqc.synth.intensity.paint_clean_scan` — sibling scans for
  the stand-in verse cohort (test-side fixture).
- **Downstream (this item enables):** item 084 (real-VerSe evaluation + "Real VerSe
  GT" verification-table closure) reuses this one-command refresh against a real
  mounted cohort.

## Environment / Hardware Dependencies

- **Real VerSe GT cohort** — an **external dataset** (not a pip dependency; large /
  licensed, never committed). Required fallback when absent (the common case,
  including all CI): the wrapper's real-VerSe steps (`verse-build` /
  `verse-evaluate`) **skip cleanly** — a structured `status == "skipped"` summary
  entry with an explicit reason, exit code unchanged (0), no traceback (AC7–AC9);
  the synthetic rebuild + evaluation always run (AC2–AC5). Every automated test
  runs against synthetic data (self-synthesized eval cohort; a stand-in
  VerSe-shaped cohort for AC10) and never requires the real dataset.
  **Full-capability verification:** an actual refresh against a mounted real VerSe
  cohort (producing a real `reference_verse_vN.json` and a real-VerSe evaluation)
  is **not** exercised here and does **not** count as verified by a green
  stand-in run. This item adds **no** verification-table row and flips none — the
  existing **"Real VerSe GT"** row in `progress.md`'s Environment-Gated Capability
  Verification table remains `❓ Unverified` and is closed by **item 084** when a
  human / CI runner with real VerSe data runs the full refresh + evaluation.

## Decisions & Trade-offs

To be updated during implementation.
