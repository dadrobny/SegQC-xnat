# Item 084 — Real-VerSe evaluation & verification-table closure (completes Stage 12)

> **Created:** 2026-07-15 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7)
> **Queue:** [`../queue/queue-010.md`](../queue/queue-010.md) · Item 084 *(fourth/final Stage-12 item — closes the stage; touches real VerSe → must degrade gracefully when the uncommitted cohort is absent)*
> **Objectives:** G3 (reference-grounded — quantify that GT segmentations pass QC
> at a high rate / low false-positive rate on **real** VerSe GT, not just the
> synthetic stand-in) and G7 (evaluable & reproducible — the FPR is computed by a
> reproducible `segqc evaluate` run and recorded as evidence)
> **Suggested branch:** `aide/084-real-verse-evaluation-stage12-closure` *(batch-specced on `aide/specs-queue-010`; execution branch created at claim time)*

---

## Description

Close **Stage 12** by (a) quantifying objective **G3** — that ground-truth VerSe
segmentations pass QC at a high rate / low false-positive rate — via the Stage-7
`segqc evaluate` path, and (b) reconciling the honest verification story:
flipping the **"Real VerSe GT"** row in `progress.md`'s Environment-Gated
Capability Verification table from `❓ Unverified` to `✅ Verified (date,
cohort/host)` **only** when a human / CI runner with real VerSe data actually ran
the evaluation.

**The G3 metric, precisely.** "GT passes at a high rate (low FPR)" is measured by
building an **expected-pass evaluation cohort from the GT segmentations
themselves** (each GT seg is a case whose `expected.expected_verdict == "pass"`,
with the candidate equal to the GT), running it through `segqc evaluate`, and
reading `metrics.false_positive_rate` from the produced `eval_report.json` — the
fraction of should-pass GT cases the pipeline wrongly flags. This is exactly the
`clean_control` FPR that item 057's calibrated-metrics block records as `0.0` on
synthetic GT; item 084 quantifies it on **real** VerSe GT.

**The honesty gate (the whole point of this item).** Real VerSe scans are large /
licensed and are **never committed** (items 082/083 policy). So:

- The **automated portion runs in CI against a synthetic VerSe-shaped stand-in
  cohort** and asserts the evaluate → FPR path is well-formed end-to-end
  (a numeric FPR in `[0, 1]`, `0.0` for the clean self-vs-self stand-in).
- The **real-VerSe clause is structurally gated** on a runtime detector
  (`real_verse_cohort_dir()`, reading the `SEGQC_VERSE_COHORT` environment
  variable): it **runs and quantifies the real FPR only when a real cohort is
  actually mounted**, and **skips cleanly** (a genuine `pytest.mark.skipif`,
  never `xfail`, never a vacuous pass) everywhere else — the CI/dev common case.
- The **"Verified" flip can never be inferred from a synthetic run.** The item
  emits a runtime **G3 verification-evidence record** whose `verified` flag is
  `True` **only** when a real cohort was evaluated *and* a non-empty cohort-id +
  ISO build-date are recorded; a machine-checkable guard (`may_mark_verified`)
  refuses to mark the row Verified for any synthetic-only record.

This mirrors the environment-gated-capability pattern of items 076/080 (radiomics
/ Docker) and 066–070's Docker gating, and the stage-closer mechanics of items
049/057/065/070/075: **`progress.md` reconciliation — including the verification
row flip — is the validator's at-merge action via the `aide` CLI, NOT a
pytest-assertable acceptance criterion**, and **`roadmap.md` (PR-gated) is not
edited by this direct-merge item**.

### The 083 / 084 boundary (settled)

Item **083** (`scripts/refresh_reference.py`) already rebuilds the synthetic
default artifact, synthesizes a self-vs-self eval cohort, runs `segqc evaluate`
over it, and — when a `--verse-cohort` is supplied — builds a versioned real-VerSe
artifact and re-runs evaluate; but its own scope-fence states it **does not
quantify a real-VerSe FPR nor flip any verification row** — that is item 084.
Item **084** therefore adds **no new running tool or production surface**: the
real evaluation is *run* by item 083's `refresh_reference.py --verse-cohort
/mnt/verse` (or a plain `segqc evaluate --cohort <verse-manifest> --cohort-id
verse-vN`). Item 084 supplies (i) the **Stage-12 G3 acceptance test module** that
exercises the evaluate → FPR path over the synthetic stand-in in CI and asserts
the real clause skips cleanly, (ii) the **G3 verification-evidence record + the
Verified-flip guard**, and (iii) the **validator-at-merge closure** of the
Stage-12 section + the "Real VerSe GT" row.

### What it is NOT (scope fence)

- **NOT a new `segqc` subcommand, new `scripts/` tool, or any `src/segqc/**`
  change.** The evaluate path (item 057) and the real-VerSe running mechanism
  (item 083) already exist; this item adds only its acceptance test module (+ the
  validator's at-merge `progress.md` edit). It introduces no new production code
  and no new dependency.
- **NOT a committed real `reference_verse_vN.json` or real VerSe data.** No large /
  licensed data is downloaded or committed; every automated test runs on synthetic
  fixtures.
- **NOT a committed FPR *threshold*.** There is no committed real-VerSe FPR target
  (the vision says "to be quantified"). The acceptance for real data is that the
  FPR is **computed and recorded**, not that it beats an invented bound. CI asserts
  only the synthetic stand-in's well-formedness + its documented `0.0` bound.
- **NOT a `progress.md` edit by the item's direct-merge work, and NOT a
  `roadmap.md` edit at all.** Reconciling the Stage-12 deliverable bullets /
  acceptance checkboxes / stage-summary / objective rows **and** flipping the
  "Real VerSe GT" verification row is the validator's at-merge action (see
  Assumptions A6), mirroring items 049/057/065/070/075 exactly.
- **NOT item 081/082/083's work** — the feature expansion (081), the build recipe
  + storage policy (082), and the one-command refresh wrapper (083) are separate
  items 084 consumes.

---

## Public surface (test-side helpers this item adds)

All in the acceptance module `tests/test_084_stage12_acceptance.py` — importable
helpers (mirroring item 075's importable `stage10_acceptance_record`), no
production code:

```python
def real_verse_cohort_dir() -> "Optional[pathlib.Path]":
    """Return the real VerSe GT cohort dir from the SEGQC_VERSE_COHORT env var
    iff it is set AND the directory exists; else None. The single runtime gate
    for the real-VerSe clause (analogue of cupy_available()/_docker_available())."""

def build_gt_pass_manifest(cohort_dir, out_dir, *,
                           seg_suffix="_seg-vert_msk.nii.gz") -> "pathlib.Path":
    """Turn a directory of GT vertebra-mask segs into an `evaluate`-shape manifest
    of expected-pass cases (candidate == gt, expected_verdict == "pass"), written
    into out_dir with gt/candidate paths relative to the manifest's own dir.
    Returns the manifest path. Used for both the synthetic stand-in (CI) and,
    when SEGQC_VERSE_COHORT is set, the real cohort."""

def g3_verification_record(*, real_cohort_present, cohort_id, build_date,
                           false_positive_rate) -> dict:
    """Return a JSON-native evidence record:
       {"real_verse_cohort_present": bool, "cohort_id": str|None,
        "build_date": str|None, "false_positive_rate": float|None,
        "verified": bool}
    where `verified` is True ONLY when real_cohort_present is True AND cohort_id
    and build_date are non-empty (see may_mark_verified)."""

def may_mark_verified(record: dict) -> bool:
    """The guard: True iff record["real_verse_cohort_present"] AND a non-empty
    record["cohort_id"] AND a non-empty record["build_date"]. Any synthetic-only
    record → False, so the 'Real VerSe GT' row can never be flipped Verified
    from a synthetic run."""
```

---

## Acceptance Criteria

_Each criterion is atomic, observable, and directly testable — one focused test
per AC. AC1–AC4 and AC6–AC10 run and pass unconditionally on this data-absent
host; AC5 concerns the genuine skip of the real-VerSe clause (which skips here).
The synthetic stand-in cohort is a tiny (2–3 subject) VerSe-shaped set built in a
`tmp_path` from `segqc.synth.clean_gt.build_clean_spine` (multi-level L1–L5) with
`segqc.synth.intensity.paint_clean_scan` sibling scans, written as
`<id>_seg-vert_msk.nii.gz` (+ `<id>_scan.nii.gz`) pairs — no real VerSe data.
`segqc evaluate` is driven in-process via `segqc.cli.main(["evaluate", …])`.
"Well-formed artifact/report" = parses as JSON without raising._

### A. Synthetic end-to-end evaluate → FPR path (CI, unconditional)

- [ ] **AC1: The Stage-12 G3 acceptance module exists with its importable
      helpers.** `tests/test_084_stage12_acceptance.py` exists and exposes callable
      `real_verse_cohort_dir`, `build_gt_pass_manifest`, `g3_verification_record`,
      and `may_mark_verified`.

- [ ] **AC2: `build_gt_pass_manifest` produces an `evaluate`-shape expected-pass
      cohort from GT segs.** Given the synthetic stand-in cohort, the helper writes
      a manifest of shape `{"manifest_version": 1, "cases": [...]}` in which
      **every** case has `expected.expected_verdict == "pass"`, its `candidate`
      file bytes equal its `gt` file bytes (GT-as-candidate), and every referenced
      `gt`/`candidate` path resolves to an existing file; there is **at least one**
      case.

- [ ] **AC3: Evaluating the stand-in cohort exits 0 and writes a well-formed
      `eval_report.json`.** `segqc.cli.main(["evaluate", "--cohort", <manifest>,
      "--out", <dir>, "--cohort-id", "verse-standin", "--build-date",
      "2026-07-15"])` returns `0` and writes `<dir>/eval_report.json` that parses as
      JSON and carries a non-empty `schema_version`, a `provenance` block, and a
      `metrics` block.

- [ ] **AC4: The report carries a well-formed G3 false-positive rate that is `0.0`
      for the clean stand-in cohort.** `metrics["false_positive_rate"]` is present
      and is a `float` in the inclusive range `[0.0, 1.0]`, and equals `0.0` for
      the clean self-vs-self expected-pass stand-in cohort (a clean GT cohort yields
      no false positives — the documented CI bound; the report's `metrics` block
      also carries a `per_mode` list, empty for a GT-only cohort).

### B. The real-VerSe clause is structurally gated (genuine skip in CI)

- [ ] **AC5: The real-VerSe evaluation clause is a GENUINE skip when no real cohort
      is configured.** The test that would evaluate a real cohort is gated by a real
      `pytest.mark.skipif` whose `mark.name == "skipif"` and whose condition
      `mark.args[0]` is a `bool` that is `True` on this host (no `SEGQC_VERSE_COHORT`
      / no mounted data) — never `xfail`, never an unconditional pass — mirroring
      `tests/test_069_container_smoke.py`'s genuine-skip proof (and item 075 AC12).

- [ ] **AC6: `real_verse_cohort_dir()` returns `None` when the dataset is absent.**
      With `SEGQC_VERSE_COHORT` unset, `real_verse_cohort_dir()` returns `None`; and
      with `SEGQC_VERSE_COHORT` set to a **nonexistent** path it also returns `None`
      (a bad/absent path is treated as "no cohort", not a crash) — verified with
      `monkeypatch.setenv`/`delenv`.

### C. G3 verification-evidence record + the Verified-flip guard

- [ ] **AC7: `g3_verification_record` returns a JSON-native evidence record with
      the required keys.** It returns a `dict` with exactly the keys
      `real_verse_cohort_present` (`bool`), `cohort_id` (`str` or `None`),
      `build_date` (`str` or `None`), `false_positive_rate` (`float` or `None`), and
      `verified` (`bool`), all JSON-serialisable (round-trips through
      `json.dumps`/`json.loads`).

- [ ] **AC8: `verified` is `True` only with a real cohort AND a recorded
      cohort-id + build-date.** `may_mark_verified(record)` returns `True` for a
      record with `real_verse_cohort_present is True` and non-empty `cohort_id` and
      non-empty `build_date`, and returns `False` whenever `real_verse_cohort_present
      is False`, **or** `cohort_id` is empty/`None`, **or** `build_date` is
      empty/`None` (parametrised over each falsifying case) — so the row can never
      be flipped Verified from a synthetic-only or under-provenanced record.

- [ ] **AC9: A synthetic-only acceptance run yields a non-verified record and
      self-reports it.** Building the record from the CI stand-in run
      (`real_cohort_present=False`) yields `real_verse_cohort_present is False`,
      `verified is False`, and `may_mark_verified(record) is False`; the record is
      `print`ed to captured test output (runtime evidence, **not** a committed
      note — mirroring item 075 A8), so the run's own output states plainly that
      the real-VerSe capability was **not** verified here.

- [ ] **AC10: The verification-record schema is consistent with the report's FPR.**
      When built from the AC3/AC4 stand-in `eval_report.json`,
      `record["false_positive_rate"]` equals the report's
      `metrics["false_positive_rate"]` (the record faithfully carries the computed
      FPR, so a recorded "Verified" is always backed by a real quantified number).

### D. Scope / regression guard

- [ ] **AC11: The item adds no production code and no new dependency.** The diff
      introduces only `tests/test_084_stage12_acceptance.py` (plus the validator's
      at-merge `progress.md` edit): `src/segqc/**` and `scripts/**` are unchanged,
      `pyproject.toml`'s `[project].dependencies` gains nothing, and the pre-existing
      `evaluate` / eval-harness test suite passes unchanged (this item is a
      test-side acceptance + validator-at-merge closure — the real running mechanism
      is item 083 / item 057, not new here).

## Assumptions  <!-- MANDATORY: confirmed decisions + pinned unbuilt interfaces (081/082/083) -->

Clarify mode was **interactive (forced)**. The three likely design questions (the
083/084 boundary, the FPR-target approach, and the flip-guard) were resolvable with
strong grounding — the queue's own "Testable" bullet for item 084 *is* the AC
skeleton, item 083's scope-fence explicitly hands the real-VerSe evaluation / G3
quantification / verification closure to 084, and item 075 is the exact stage-closer
precedent — so they are **settled and recorded here** rather than blocked (mirroring
item 082's forced-interactive resolution). Several **pin an interface**; the
builder/validator **hand back if reality diverged**.

- **A1 — 083/084 boundary [settled].** Item 084 adds **no new running tool or
  `src/segqc/**` change**. The real-VerSe evaluation is *run* by item 083's
  `scripts/refresh_reference.py --verse-cohort <dir>` (which already does
  verse-build + verse-evaluate) or a plain `segqc evaluate` (item 057). Item 084
  owns: the Stage-12 G3 **acceptance test** (synthetic path exercised in CI; real
  path gated), the G3 **verification-evidence record + guard**, and the
  **validator-at-merge closure**. Rationale: item 083's spec explicitly fences out
  "the real-VerSe evaluation / verification-table closure … is item 084"; item 075
  is the precedent for a test-side + validator-at-merge stage-closer.

- **A2 — the G3 metric = FPR on a GT-as-expected-pass cohort [settled].** "GT
  passes at a high rate (low FPR)" is quantified by building an expected-pass
  evaluate cohort from the GT segs themselves (`candidate == gt`,
  `expected_verdict == "pass"`) and reading `metrics.false_positive_rate` from
  `segqc evaluate`'s `eval_report.json` — the FP/(FP+TN) over the should-pass GT
  set (item 054's `CohortMetrics.false_positive_rate`; item 057 records this as the
  `clean_control` FPR = `0.0` on synthetic GT). Per-mode sensitivity is "where
  applicable"; a GT-only cohort has no injected failures, so `per_mode` is present
  but empty and overall `sensitivity` is `None` — recorded as-is, not over-claimed.

- **A3 — FPR-target approach [settled: quantify, don't threshold].** There is **no
  committed real-VerSe FPR target** (the vision says "to be quantified"), so no
  pass/fail threshold is invented. CI asserts only the **synthetic** stand-in's
  well-formedness and its documented `0.0` bound (a clean expected-pass cohort has
  no false positives, consistent with item 057's `clean_control` FPR and item 083
  AC5). The **real** FPR's acceptance is that it is *computed and recorded* (in the
  eval report, and — validator-at-merge — into `progress.md`'s Stage-12
  metrics note), not that it beats a bound.

- **A4 — real-cohort detection via `SEGQC_VERSE_COHORT` env var [settled].** The
  single runtime gate is `real_verse_cohort_dir()` reading the `SEGQC_VERSE_COHORT`
  environment variable (returns the path iff set **and** the dir exists, else
  `None`) — the dataset analogue of `cupy_available()` (item 075) /
  `_docker_available()` (item 069/080). The real-VerSe test is
  `@pytest.mark.skipif(real_verse_cohort_dir() is None, …)`; on CI/dev it skips
  cleanly (AC5), and a nonexistent path is treated as absent, not a crash (AC6).

- **A5 — the Verified-flip guard [settled].** The "Real VerSe GT" row may be flipped
  to `✅ Verified` **only** when a real cohort was actually evaluated with a recorded
  non-empty `cohort_id` + ISO `build_date`. This is machine-checkable via
  `may_mark_verified(record)` (AC8): any synthetic-only record → `False`. The
  evidence is a **runtime record printed to captured output** (AC9), not a committed
  host-specific note (would go stale; mirrors item 075 A8). This is the guard the
  queue's "a check asserts the verification-table row is only marked Verified when
  accompanied by a recorded cohort id + date" refers to.

- **A6 — `progress.md` reconciliation (incl. the verification-row flip) is a
  validator-at-merge action, NOT a pytest AC [049/057/065/070/075 precedent].**
  At merge the validator, via the `aide` CLI, updates `docs/aide/progress.md`'s
  Stage-12 section — the four deliverable bullets (081–084) → ✅, the three
  acceptance checkboxes, the Stage-12 stage-summary row, and the G3/G7
  objective-coverage rows as warranted — and reconciles the **"Real VerSe GT"** row
  in the Environment-Gated Capability Verification table. Following item 075 A9's
  precedent (the GPU row), that row is flipped to `✅ Verified (date, cohort/host)`
  **only if** item 084's gated real-VerSe clause actually ran (real cohort present,
  a real FPR quantified with a recorded cohort-id + date) on the merging host;
  on any host where the clause skipped (this CI/dev environment), the row stays
  `❓ Unverified` **even though Stage 12 itself reaches ✅** on its synthetic-stand-in
  path — the two statuses are intentionally decoupled (the table's own header note).
  This bookkeeping is deliberately **not** an AC (a spec cannot pytest-assert its
  own progress-doc edits). **`roadmap.md`** (PR-gated framework file) is **not**
  edited by this item.

- **A7 — real VerSe is not committed → synthetic end-to-end in CI + gated real
  clause.** Every automated test runs against a synthetic VerSe-shaped stand-in
  cohort built from the production synth builders; no real, large, or licensed data
  is downloaded or committed, and no `reference_verse_*.json` is committed by this
  item. The real-VerSe clause runs only on a data-holding host (AC5 gate).

- **A8 — pinned upstream interface, item 081 (specced, NOT yet merged; hand back if
  diverged):** `segqc.reference.schema.SCHEMA_VERSION == "1.2"` with the morphology
  family (`largest_component_fraction`, `component_count`, `eigenvalue_ratio`)
  default-on in `build_reference`. Item 084 does not assert the artifact family set
  directly (it evaluates GT via `segqc run`/`evaluate`, not the reference build), so
  a minor 081 divergence does not break its ACs; but the real evaluation is only
  *meaningful* against the 081-expanded reference, so the builder notes the pin.

- **A9 — pinned upstream interface, item 082 (specced, NOT yet merged; hand back if
  diverged):** the real VerSe vertebra-mask suffix is `_seg-vert_msk.nii.gz` and CT
  siblings are staged as `<id>_scan.nii.gz` (item 082's staging convention);
  `build_gt_pass_manifest`'s default `seg_suffix` matches. If 082 changed the suffix
  convention, `build_gt_pass_manifest` needs the matching default and the builder
  hands back.

- **A10 — pinned upstream interface, item 083 (specced, NOT yet merged; hand back if
  diverged):** `scripts/refresh_reference.py --verse-cohort <dir>` is the documented
  running mechanism for the real evaluation (verse-build + verse-evaluate), so item
  084 need not add one. Item 084 does not import 083's script; it re-exercises the
  underlying `segqc evaluate` surface directly. If 083's real-cohort running
  mechanism diverged, only the Assumptions prose (not an AC) is affected.

- **A11 — pinned upstream interfaces (merged ✅):**
  - **Item 057** — the `segqc evaluate` subcommand (`--cohort <manifest.json> --out
    <dir> [--cohort-id <label>] [--build-date <YYYY-MM-DD>]`) → `evaluate_cohort` →
    `compute_cohort_metrics`, writing `<out>/eval_report.json` whose
    `metrics.false_positive_rate` is `CohortMetrics.to_dict()`'s FPR (a `float`, or
    `None` only when the expected-pass set is empty — not the case here), plus
    `metrics.per_mode`; and the `segqc.eval.cohort` manifest shape
    (`manifest_version`, `cases[].case_id/.gt/.candidate/.expected.expected_verdict`;
    gt/candidate paths resolved relative to the manifest file's own directory).
  - **Item 036** — `segqc.synth.clean_gt.build_clean_spine(*, levels, spacing,
    curve_amplitude_mm, convention)` → `CleanSpine` with `.seg_img` — the builder
    the stand-in GT cohort is synthesized from.
  - **Item 058** — `segqc.synth.intensity.paint_clean_scan(seg_img, *, seed=0, …)`
    for the stand-in cohort's sibling scans.
  - **Item 069** — `tests/test_069_container_smoke.py`'s genuine-skip proof, the
    precedent AC5 mirrors for the `SEGQC_VERSE_COHORT`-gated marker.
  - **Items 049/057/065/070/075** — the Stage-6/7/8/9/10 closers whose
    `progress.md`-reconciliation-at-merge (incl. the env-gated row flip) and
    no-`roadmap.md`-edit precedent this item follows exactly (A6).

## Implementation Steps

Intended path: a **single new test module** `tests/test_084_stage12_acceptance.py`.
**No** change to `src/segqc/**`, no new `scripts/` tool, no committed artifact.
(The only non-test edit for the whole item is the **validator's** at-merge
`progress.md` reconciliation — see A6 — which the builder/test-writer do not make.)

1. **Module skeleton + importable helpers** (mirror item 075's acceptance module):
   `real_verse_cohort_dir()` (read `SEGQC_VERSE_COHORT`, return an existing dir else
   `None`); `build_gt_pass_manifest(cohort_dir, out_dir, *, seg_suffix=
   "_seg-vert_msk.nii.gz")` (discover `*<seg_suffix>` files, write GT-as-candidate
   expected-pass cases into an `evaluate`-shape manifest with paths relative to the
   manifest's own dir, return the manifest path); `g3_verification_record(*,
   real_cohort_present, cohort_id, build_date, false_positive_rate)` (assemble the
   JSON-native record, computing `verified` via `may_mark_verified`);
   `may_mark_verified(record)` (the guard: real-present AND non-empty cohort-id AND
   non-empty build-date).
2. **Stand-in cohort fixture** (test-side): build a tiny 2–3 subject VerSe-shaped
   cohort in `tmp_path` via `build_clean_spine` (L1–L5) + `paint_clean_scan`, saved
   as `<id>_seg-vert_msk.nii.gz` + `<id>_scan.nii.gz` pairs (the same shape items
   082/083 use).
3. **Synthetic evaluate path (AC2–AC4):** call `build_gt_pass_manifest` over the
   stand-in, drive `segqc.cli.main(["evaluate", "--cohort", <manifest>, "--out",
   <dir>, "--cohort-id", "verse-standin", "--build-date", "2026-07-15"])`, parse
   `eval_report.json`, assert exit 0, well-formedness, and FPR `== 0.0`.
4. **Gated real clause (AC5, + the positive assertion for data-holders):** define
   `requires_verse = pytest.mark.skipif(real_verse_cohort_dir() is None, reason=
   "real VerSe GT cohort not mounted (set SEGQC_VERSE_COHORT)")`; a `@requires_verse`
   test that, on a data-holding host, builds the manifest from the real cohort, runs
   `segqc evaluate --cohort-id verse-vN`, asserts a well-formed FPR, and asserts the
   record's `verified is True`; skips cleanly on CI/dev. Add the AC5 structural
   proof (`requires_verse.mark.name == "skipif"`, `isinstance(mark.args[0], bool)`,
   `is True` here — mirror `tests/test_069_container_smoke.py`).
5. **Record + guard tests (AC6–AC10):** `real_verse_cohort_dir()` env behaviour
   (AC6); record key/type shape + JSON round-trip (AC7); `may_mark_verified`
   truth-table parametrised over each falsifying case (AC8); the synthetic-only
   record is non-verified and `print`ed (AC9); the record's FPR equals the report's
   FPR (AC10).
6. **Scope guard (AC11):** assert (via a light diff/source check) no `src/segqc/**`
   or `scripts/**` file is added/modified by this item and `pyproject.toml`
   `[project].dependencies` is unchanged; rely on the validator's full-suite run for
   the "existing evaluate tests pass unchanged" clause.
7. **No `progress.md` / `roadmap.md` edits here** (A6) — the validator reconciles
   `progress.md` Stage 12 at merge via the `aide` CLI, including flipping the
   "Real VerSe GT" row to `✅ Verified` **only** if the gated real clause actually
   ran on the merging host (else left `❓ Unverified`).

## Testing Strategy

_The spec-author does not run `pytest`. The test-writer authors
`tests/test_084_stage12_acceptance.py`; the builder makes no production edit; the
validator runs the full suite and reconciles `progress.md`._ One module, one
focused test per AC, mirroring the `test_0NN_*.py` convention. All real-VerSe
behaviour is `SEGQC_VERSE_COHORT`-gated and skips cleanly on this data-absent host.
Use `monkeypatch.setenv`/`delenv` for hermetic env handling; drive `segqc evaluate`
in-process via `segqc.cli.main` (not a subprocess) into `tmp_path`.

- **AC1** — import the module by name; assert the four helpers are callable.
- **AC2** — build the stand-in cohort; call `build_gt_pass_manifest`; parse the
  manifest and assert `manifest_version == 1`, ≥1 case, every case
  `expected.expected_verdict == "pass"` with `gt` bytes == `candidate` bytes, and
  every referenced path exists (resolved relative to the manifest dir).
- **AC3** — `main(["evaluate", …])` returns `0`; `eval_report.json` parses with a
  non-empty `schema_version`, a `provenance` block, and a `metrics` block.
- **AC4** — `metrics["false_positive_rate"]` is a `float` in `[0.0, 1.0]` and
  `== 0.0`; `metrics["per_mode"]` is a list (empty for the GT-only cohort).
- **AC5** — structural: `requires_verse.mark.name == "skipif"`,
  `isinstance(requires_verse.mark.args[0], bool)`, `... is True` on this host
  (mirror `tests/test_069_container_smoke.py`).
- **AC6** — `monkeypatch.delenv("SEGQC_VERSE_COHORT", raising=False)` →
  `real_verse_cohort_dir() is None`; `monkeypatch.setenv` to a nonexistent path →
  still `None`.
- **AC7** — build a record; assert the exact key set + value types and a
  `json.dumps`/`json.loads` round-trip equal to the original.
- **AC8** — parametrised truth-table: `(present, cohort_id, build_date)` →
  expected `may_mark_verified` — `True` only for `(True, "verse-vN", "2026-07-15")`;
  `False` for `real_present=False`, for empty/`None` `cohort_id`, and for
  empty/`None` `build_date`.
- **AC9** — build the record with `real_cohort_present=False`; assert
  `real_verse_cohort_present is False`, `verified is False`,
  `may_mark_verified(...) is False`; capture stdout and assert the record was
  printed (runtime evidence).
- **AC10** — build the record from the AC3/AC4 report's FPR; assert
  `record["false_positive_rate"] == metrics["false_positive_rate"]`.
- **AC11** — assert (git/diff or path check) that the item adds only
  `tests/test_084_stage12_acceptance.py` under `src/segqc/**` + `scripts/**` scope,
  and parse `pyproject.toml` to assert `[project].dependencies` gained nothing.

**Adversarial / edge cases to include:**
- **Nonexistent / empty `SEGQC_VERSE_COHORT`** — a set-but-nonexistent path returns
  `None` (treated as absent, AC6), and an existing-but-empty dir passed to
  `build_gt_pass_manifest` yields an **empty** `cases` list without a traceback
  (the caller — the gated clause — then treats it as "no evaluable GT").
- **Guard non-vacuity** — assert `may_mark_verified` returns `False` for a record
  that has a real cohort but a **missing** `build_date` (and vice-versa), so a
  partially-provenanced real run cannot flip the row.
- **FPR `None` handling** — if a constructed cohort's expected-pass set were empty,
  `metrics.false_positive_rate` would be `None`; the stand-in cohort deliberately
  contains expected-pass GT cases so the value is a `float` — assert it is not
  `None`, guarding against a silently-vacuous "verified" on an empty cohort.
- **Determinism** — two evaluate runs over the same stand-in manifest produce equal
  `metrics.false_positive_rate` (the fixed `--build-date` keeps provenance stable).
- **Env hygiene** — `SEGQC_VERSE_COHORT` is not left mutated in `os.environ` after
  any test (monkeypatch teardown); assert directly for at least one case.

## Dependencies

- **Item 081 (🚧 specced ahead in this batch; must be built + merged for the
  expanded reference the real evaluation is meaningfully judged against):** pinned
  in Assumptions (A8). AC-neutral (084 evaluates GT via the pipeline, not the
  reference build), but the builder notes the pin.
- **Item 082 (🚧 specced ahead in this batch; the real-VerSe build recipe + the
  `_seg-vert_msk.nii.gz` suffix / `_scan.nii.gz` staging convention `build_gt_pass_
  manifest` follows):** pinned in Assumptions (A9).
- **Item 083 (🚧 specced ahead in this batch; the one-command real-VerSe running
  mechanism — `refresh_reference.py --verse-cohort` — this item's real evaluation
  reuses rather than re-implements):** pinned in Assumptions (A10).
- **Item 057 (✅):** the `segqc evaluate` subcommand + `evaluate_cohort` +
  `compute_cohort_metrics` and the `segqc.eval.cohort` manifest shape /
  relative-path resolution — the evaluation surface and the FPR metric asserted in
  AC3/AC4. The closest closer-precedent (`clean_control` FPR = 0.0).
- **Items 053/054 (✅):** the evaluation harness (`evaluate_cohort`) and
  `metrics.false_positive_rate` / `per_mode` — the machinery producing the G3
  numbers.
- **Item 036 (✅):** `segqc.synth.clean_gt.build_clean_spine` — the stand-in GT
  cohort builder (no `tests/corpus` coupling).
- **Item 058 (✅):** `segqc.synth.intensity.paint_clean_scan` — sibling scans for
  the stand-in cohort.
- **Item 069 (✅):** `tests/test_069_container_smoke.py`'s genuine-skip proof — the
  precedent AC5 mirrors for the `SEGQC_VERSE_COHORT`-gated marker.
- **Items 049 / 057 / 065 / 070 / 075 (✅):** the Stage-6/7/8/9/10 closers whose
  `progress.md`-reconciliation-at-merge (incl. item 075's env-gated row flip) and
  no-`roadmap.md`-edit precedent this item follows exactly (A6).

## Environment / Hardware Dependencies

- **Real VerSe GT cohort** — an **external dataset** (not a pip dependency; large /
  licensed, never committed). Required fallback when absent (the common case,
  including all CI): the real-VerSe evaluation clause **skips cleanly** — a genuine
  `pytest.mark.skipif` gated on `real_verse_cohort_dir()` (the `SEGQC_VERSE_COHORT`
  env var), never a failure, never a vacuous pass (AC5); the synthetic stand-in
  evaluate → FPR path always runs (AC2–AC4). Every automated test runs against
  synthetic data and never requires the real dataset.
  **Full-capability verification:** an actual `segqc evaluate` over a mounted real
  VerSe GT cohort — quantifying the real G3 false-positive rate — is **not**
  exercised in CI and a green stand-in run does **not** count as verification. This
  item **closes** the existing **"Real VerSe GT"** row in `progress.md`'s
  Environment-Gated Capability Verification table: the validator flips it to
  `✅ Verified (date, cohort/host)` **only** when a human / CI runner with real VerSe
  data actually ran the gated clause (a real FPR quantified, with a recorded
  cohort-id + date, guarded by `may_mark_verified`); on a data-absent host the row
  stays `❓ Unverified` even as Stage 12 reaches ✅ on its synthetic path (the two
  statuses are decoupled — see A6 and the table's header note).

## Decisions & Trade-offs

To be updated during implementation.
