# Item 042 — Golden-file JSON snapshots & determinism harness *(completes Stage 5)*

> **Created:** 2026-07-10 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 042 *(the last item in queue-004; depends on 040/041; closes Stage 5)*
> **Objectives:** G7 (evaluable & regression-testable — output determinism is
> locked and the full Stage 4→5 emitted-JSON behaviour is pinned) and the
> regression-net half of G2 (every committed fixture's report is snapshot-locked)
> **Suggested branch:** `aide/042-golden-file-json-snapshots-determinism`

---

## Description

Capture **golden-file JSON report snapshots** for every case in the committed
corpus (item 040) and add a **determinism harness** that re-runs the QC pipeline
over each committed fixture and asserts the emitted JSON report is stable —
**byte-identical across repeated runs** and **equal to the committed golden**
(modulo an explicitly-normalised, documented set of volatile fields). Provide a
documented, **one-command golden-update path** so intentional snapshot refreshes
are deliberate and reviewable. This locks output determinism and pins the full
Stage 4→5 behaviour, **completing Stage 5**.

Three deliverables:

1. **A packaged snapshot/determinism library** — a new module
   `src/segqc/synth/golden.py` (importable G7 tooling, the natural sibling of
   item 040's `corpus.py` and item 041's `regression.py`). It reproduces
   `segqc run`'s JSON-report construction for one manifest case, **canonicalises**
   the report (sorted keys + normalisation of a documented volatile-field
   allow-list), reads/writes the committed goldens, and exposes the determinism
   predicates the pytest suite asserts on.

2. **The committed golden corpus** — one `tests/corpus/golden/<case_id>.json` per
   manifest case (its natural home, reserved by item 040's Assumptions), generated
   by that module's one-command regeneration entry point
   (`python -m segqc.synth.golden`) and checked in so its diffs are reviewable.

3. **The parametrised determinism pytest suite** —
   `tests/test_042_golden_determinism.py`, parametrised over the committed
   manifest, that asserts (per case) two runs are byte-identical, the fresh output
   equals the committed golden, each golden validates against the report schema,
   and the harness **bites** (a deleted or mutated golden fails).

### What "the emitted JSON" actually is (read the real schema, don't guess)

The JSON report `segqc run` writes to `<out>/segqc_report.json` is built by
`segqc.report.serialize_report(verdict, case_id, config, features, findings)`
(item 009, extended by items 016/035) and validated at build time against the
package-data schema `src/segqc/report_schema_v0.json`. That schema has
`additionalProperties: false` at the top level and its only keys are:

| key | source | volatile? |
|---|---|---|
| `schema_version` | `const "0.1"` | no (pinned constant) |
| `config_version` | `config.schema_version` (`"0.1"` for the bundled default) | no (pinned by config) |
| `case_id` | **CLI derives it from the scan filename stem** | **input-derived** (see below) |
| `verdict` | aggregated `Verdict.overall.label` | no (deterministic) |
| `reasons` | case-level `Reason`s (labels sorted) | no |
| `per_label` | per-label `Reason`s (labels sorted) | no |
| `features` | Stage 2/3 feature block (floats) | no (deterministic floats) |
| `findings` | `[Finding.to_dict() …]` (labels sorted) | no |

**Material finding:** the v0 report carries **no wall-clock timestamp, no absolute
path, and no tool version** — `additionalProperties: false` structurally
guarantees nothing volatile sneaks in, and `report.py` already sorts every
`labels`/`per_label` collection for determinism (its design decisions #3/#4). The
queue's anticipated "volatile fields such as timestamps / absolute paths / tool
version" are therefore **not present** in the current schema. The genuine
determinism surface is:

- **Floating-point values in the `features` block** — computed by the pipeline,
  which is documented deterministic (`pipeline.py` design decision #5: "two calls
  on the same inputs return equal results"). `json.dumps` serialises floats via
  round-trippable `repr`, so byte-identical output holds run-to-run. This item
  **locks** that with the two-successive-runs AC.
- **`case_id`** — the one input-derived field. The CLI sets it from the scan
  filename stem; because all nine corpus cases share one `base_scan.nii.gz`, the
  raw CLI would stamp every report `case_id == "base_scan"`. This item **fixes**
  `case_id` to the corpus `case_id` (the concrete instance of the queue's
  "absolute-path" canonicalisation), so goldens are per-case and stable.

The canonicaliser is still built as the documented **seam** the queue asks for
(`VOLATILE_POINTERS`, applied before comparison), so that if a future schema adds
a `generated_at`/`tool_version` field it is normalised in exactly one place —
but for report schema v0 that allow-list is **empty** and determinism holds with
no normalisation. This honest fact is recorded in Assumptions and asserted (a real
report contains no volatile-looking key).

### Golden scope — all nine cases, three flagged "pipeline-blind" (the second material decision)

The corpus has nine cases; six are `detection == "pipeline"` and three
(`mode1_displace`, `mode4_relabel_swap`, `mode8_force_overlap`) are
`detection == "reconstructed_record"` — structurally invisible to plain `run_qc`
(items 038/039/040/041). A golden JSON is a **direct output of `run_qc` on the
committed fixture**, and it exists for all nine cases (the three reconstructed
fixtures produce a valid, mode-blind report: `verdict == "pass"`, no designated
rule fired).

**Decision: commit goldens for all nine cases**, with the three reconstructed
goldens explicitly marked and asserted as **known pipeline-blind snapshots**.
Rationale:

- A golden's job is to *pin exactly what the pipeline emits for each committed
  fixture and catch any drift*. The reconstructed fixtures' pipeline JSON is a
  real, meaningful output whose stability we want locked as much as any other — if
  a future pipeline change suddenly made `force_overlap` detectable, its golden
  would flag the change as a deliberate refresh requiring review, which is exactly
  the reviewable signal Stage 5 is for.
- Omitting them would leave three committed fixtures with *no* output-stability
  guard, weakening the "pins the full Stage 4→5 behaviour" milestone.

The three reconstructed goldens must **not** be conflated with "detects the failure
mode": the manifest's `detection` field already separates them, and this item adds
an AC asserting each reconstructed golden is pipeline-blind (`verdict == "pass"`
and no golden `finding.rule_id` is in that case's `expected_rule_ids`). The
determinism/equality guarantees apply uniformly to all nine.

### Scope boundary — what this item is **not**

- **Not a change to the report, pipeline, corpus, or regression modules.** It
  consumes `segqc.report.serialize_report`, `segqc.pipeline.run_qc`,
  `segqc.io.load_case`, `segqc.empty.check_empty`, `segqc.config`, the item-040
  corpus/manifest, and item-041 `regression.loaded_seg_image` **unchanged**. It
  edits none of `report.py`, `pipeline.py`, `cli.py`, `corpus.py`,
  `regression.py`, or any operator/rule/extractor/config module, and adds no
  `Perturbation`/`Rule`.
- **Not a fix for the reconstructed-record limitation** (out-of-scope Stage 4
  change). It faithfully snapshots the pipeline-blind JSON for those three cases.
- **Not a new report field, schema version, or schema change.** The v0 report
  shape is snapshotted as-is.
- **Not a CLI-subprocess end-to-end test.** The report is reconstructed
  **in-process** (mirroring `cli._handle_run`'s steps) so `case_id` can be fixed
  per case and the same logic drives the drift/guard tests (consistent with item
  041's in-process choice).

---

## Public interface (the snapshot/determinism surface)

New module `src/segqc/synth/golden.py`, additively re-exported from
`segqc.synth.__init__` (matching the item-040/041 re-export style).

```python
GOLDEN_DIRNAME: str = "golden"
GOLDEN_DIR: Path                      # CORPUS_DIR / "golden"  (== tests/corpus/golden)
VOLATILE_POINTERS: tuple[tuple[str, ...], ...] = ()   # documented volatile-field allow-list; EMPTY for report schema v0
VOLATILE_SENTINEL: str = "<normalised>"               # value volatile pointers are replaced with

def build_report_for_case(case: dict, config=None, corpus_dir: Path = CORPUS_DIR) -> dict:
    """Reproduce `segqc run`'s JSON-report construction for one manifest case,
    in-process, with case_id fixed to case["case_id"]:
      1. seg_img = regression.loaded_seg_image(case, corpus_dir)   # Stage 0 loader
      2. cfg     = config or bundled_default_config()
      3. base_reasons = check_empty(seg_img, cfg) -> Reason list   # mirrors cli step 3-4
      4. case_result, features = run_qc(seg_img, cfg, base_reasons=base_reasons)
      5. findings = [f.to_dict() for f in case_result.findings]
      6. return serialize_report(case_result.verdict, case["case_id"], cfg,
                                 features=features, findings=findings)
    The returned dict is schema-validated by serialize_report itself."""

def canonical_json(report: dict, *, volatile_pointers=VOLATILE_POINTERS) -> str:
    """Canonical text form of a report for byte comparison: deep-copy, replace the
    value at each present pointer in volatile_pointers with VOLATILE_SENTINEL, then
    json.dumps(sort_keys=True, indent=2, ensure_ascii=False) + "\n". Idempotent."""

def golden_path(case_id: str, golden_dir: Path = GOLDEN_DIR) -> Path:
    """golden_dir / f"{case_id}.json"."""

def read_golden_text(case_id: str, golden_dir: Path = GOLDEN_DIR) -> str:
    """Read the committed golden's UTF-8 text. Raises FileNotFoundError if absent
    (a missing golden must fail loudly, never silently pass)."""

def load_golden(case_id: str, golden_dir: Path = GOLDEN_DIR) -> dict:
    """json.loads(read_golden_text(...))."""

def check_case_golden(case: dict, config=None, golden_dir: Path = GOLDEN_DIR,
                      corpus_dir: Path = CORPUS_DIR) -> bool:
    """True iff canonical_json(build_report_for_case(case)) equals the committed
    golden text. Propagates FileNotFoundError when the golden is missing."""

def write_goldens(dest: Path = GOLDEN_DIR, config=None, corpus_dir: Path = CORPUS_DIR) -> list[Path]:
    """Regenerate one dest/<case_id>.json per manifest case (canonical_json bytes,
    UTF-8). Deterministic. Returns the written paths."""

def main(argv=None) -> int:
    """`python -m segqc.synth.golden [--out DIR]` — the one-command golden-update
    path (default --out == GOLDEN_DIR). Returns 0 on success."""
```

Canonical form matches the item-040 manifest house style: `json.dumps(...,
indent=2, sort_keys=True)` + trailing `\n`, written via `write_bytes` on the
UTF-8 encoding (exact `\n` line endings on every supported Python, per item 040's
`write_text(newline=…)`-is-3.10+ decision).

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. "A case" is a dict from
`load_manifest()["cases"]`; "its golden" is `tests/corpus/golden/<case_id>.json`.
Group tests are `@pytest.mark.parametrize`d over `load_manifest()["cases"]`, so a
new manifest case auto-extends coverage. The report schema is
`src/segqc/report_schema_v0.json`, loaded via `importlib.resources`._

### A. Report construction mirrors `segqc run`

- [ ] **AC1: Every case's report validates against the schema.** For every case,
      `build_report_for_case(case)` returns a dict that passes
      `jsonschema.validate(report, <report_schema_v0>)` without raising.

- [ ] **AC2: The fixed/pinned fields are correct.** For every case, the report's
      `case_id == case["case_id"]`, `schema_version == "0.1"`, and
      `config_version == bundled_default_config().schema_version`.

- [ ] **AC3: The report carries the full `segqc run` shape.** For every case, the
      report contains both a `features` key (a dict with `features_version`) and a
      `findings` key equal to `[f.to_dict() for f in run_qc(loaded seg,
      bundled_default_config())[0].findings]`.

### B. Determinism (locks output stability)

- [ ] **AC4: Two successive runs are byte-identical.** For every case,
      `canonical_json(build_report_for_case(case)) ==
      canonical_json(build_report_for_case(case))` (re-running the pipeline over
      the committed fixture yields identical canonical JSON).

- [ ] **AC5: The canonical form is a fixed point.** For every case,
      `canonical_json(report) == canonical_json(json.loads(canonical_json(report)))`
      (parsing then re-canonicalising is a no-op; keys are sorted).

### C. Golden corpus completeness, storage & validity

- [ ] **AC6: There is exactly one committed golden per manifest case — no more, no
      fewer.** The set of `*.json` filename stems under `GOLDEN_DIR` equals the set
      of committed `case_id`s (nine files; no orphan and no missing golden).

- [ ] **AC7: Every committed golden is valid JSON and validates against the
      schema.** For every committed golden file, `json.loads(text)` succeeds and
      `jsonschema.validate(<parsed>, <report_schema_v0>)` does not raise.

- [ ] **AC8: Every committed golden's `case_id` matches its filename.** For every
      golden file, `load_golden(stem)["case_id"] == stem` and `stem` is a manifest
      `case_id`.

### D. Freshly-built output equals the committed golden

- [ ] **AC9: Fresh canonical JSON equals the committed golden bytes.** For every
      case, `canonical_json(build_report_for_case(case))` (UTF-8 encoded) equals
      the committed `tests/corpus/golden/<case_id>.json` bytes
      (`check_case_golden(case)` is `True`).

### E. Volatile-field canonicalisation seam (documented; empty for v0)

- [ ] **AC10: `canonical_json` normalises the pointers it is given.** With an
      explicit `volatile_pointers=(("generated_at",),)`, two synthetic report dicts
      that differ **only** in `report["generated_at"]` produce identical
      `canonical_json(...)` output; the normalised value is `VOLATILE_SENTINEL`.

- [ ] **AC11: The v0 report is already volatile-field-free.** `VOLATILE_POINTERS`
      equals `()`, and for every case no key in a documented denylist
      (`{"timestamp", "generated_at", "created", "date", "datetime", "path",
      "abspath", "tool_version", "hostname", "user"}`) appears at any nesting depth
      of `build_report_for_case(case)` — so determinism (AC4/AC9) holds with no
      normalisation applied.

### F. One-command update path & the harness bites

- [ ] **AC12: The update entry point regenerates matching goldens.**
      `main(["--out", str(tmp)])` returns `0`, writes one `<case_id>.json` per
      manifest case under `tmp`, and every written file's bytes equal
      `canonical_json(build_report_for_case(case))` for its case.

- [ ] **AC13: Regeneration reproduces the committed goldens byte-for-byte.** For
      every case, the file `write_goldens(tmp)` produces is byte-identical to the
      committed `GOLDEN_DIR/<case_id>.json` (the checked-in goldens are exactly what
      the documented command regenerates).

- [ ] **AC14: A missing golden fails loudly.** For a case whose golden is absent
      from the target directory (e.g. a fresh `tmp`), `check_case_golden(case,
      golden_dir=tmp)` raises `FileNotFoundError` (a deleted golden cannot pass
      silently).

- [ ] **AC15: A mutated golden is caught.** For a case whose golden file (a copy in
      `tmp`) has been altered, `check_case_golden(case, golden_dir=tmp)` returns
      `False`.

### G. The reconstructed goldens are known pipeline-blind snapshots

- [ ] **AC16: Reconstructed-record goldens lock the mode-blind pipeline JSON.** For
      every `detection == "reconstructed_record"` case (modes 1, 4, 8), its golden's
      `verdict == "pass"` and **no** golden `finding` has a `rule_id` in
      `case["expected_rule_ids"]` — i.e. the golden faithfully snapshots the
      pipeline-blind output and is not to be read as detecting the mode.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **MATERIAL DECISION 1 — the v0 report has no timestamp/path/tool-version fields,
  so the "volatile-field" allow-list is EMPTY; the canonicaliser is still built as
  the documented seam.** Read from the real code: `serialize_report` (item 009)
  emits exactly `schema_version` (const `"0.1"`), `config_version`, `case_id`,
  `verdict`, `reasons`, `per_label`, optional `features`, optional `findings`, and
  `report_schema_v0.json` sets `additionalProperties: false`, so no wall-clock /
  path / tool-version field exists to normalise. Determinism instead rests on (a)
  deterministic pipeline floats in `features` (`pipeline.py` design decision #5)
  serialised via round-trippable `repr`, and (b) `report.py` already sorting all
  `labels`/`per_label` collections. `VOLATILE_POINTERS` is therefore `()` for v0
  (AC11), and `canonical_json` applies it as a no-op seam that a future
  `generated_at`/`tool_version` field would plug into in one place (AC10 proves the
  mechanism). The validator should surface that the queue's literal
  "timestamps/absolute paths/tool version" set does not exist in this schema.

- **MATERIAL DECISION 2 — goldens are committed for ALL NINE cases; the three
  `reconstructed_record` cases are marked and asserted as pipeline-blind
  snapshots.** A golden is a direct `run_qc` output and exists for every fixture;
  committing all nine maximises drift coverage (every committed fixture gets an
  output-stability guard) and gives the "pins the full Stage 4→5 behaviour"
  milestone its intended breadth. The three reconstructed goldens capture the
  mode-blind pipeline JSON (`verdict == "pass"`, no designated rule fired) — locked
  by AC16 — and must not be conflated with detecting the mode (the manifest's
  `detection` field is the discriminator). The alternative (six pipeline goldens
  only) was rejected because it would leave three committed fixtures unguarded
  against output drift. The validator should surface this scope choice.

- **`case_id` is fixed to the corpus `case_id`, not the scan filename stem.** The
  CLI (`cli._handle_run` step 6) derives `case_id` from the scan filename; all nine
  cases share `base_scan.nii.gz`, so the raw CLI would stamp every report
  `case_id == "base_scan"`. Fixing `case_id = case["case_id"]` is the one
  "input-derived field" normalisation that makes per-case goldens possible and
  stable — the concrete instance of the queue's "absolute-path" canonicalisation.
  Every other field is reproduced exactly as `segqc run` would emit it.

- **The report is reconstructed in-process, mirroring `cli._handle_run` steps
  3–7**, rather than shelling out to `segqc run`: load the committed seg via the
  Stage 0 loader (reusing item 041's `regression.loaded_seg_image`, which rebuilds
  the `Nifti1Image` with the mandatory explicit `dtype=`), run `check_empty` to
  derive `base_reasons`, `run_qc(seg_img, cfg, base_reasons=base_reasons)`, and
  `serialize_report(verdict, case_id, cfg, features, findings)`. This is chosen so
  `case_id` can be fixed per case (impossible through the CLI given the shared scan)
  and so the same library logic drives the drift/guard tests — consistent with item
  041's in-process rationale. The `int32`-vs-`int64` seg dtype difference between
  the CLI (`astype("int32")`) and `loaded_seg_image` (`dtype=seg.data.dtype`) is
  immaterial to the JSON because every corpus label value (20–28) is representable
  in both, yielding identical `np.unique` labels and identical feature floats. If a
  reviewer wants a CLI-subprocess smoke test, it is a mechanical additive follow-up.

- **Goldens live at `tests/corpus/golden/<case_id>.json`** — the home item 040's
  Assumptions explicitly reserved ("giving item 042's golden snapshots a natural
  home at `tests/corpus/golden/`"), under `tests_dir` beside the corpus fixtures so
  the shipped XNAT container stays lean. `GOLDEN_DIR` is resolved from
  `corpus.CORPUS_DIR` (`CORPUS_DIR / "golden"`), so the goldens relocate with the
  corpus. As with item 040's generated fixtures, these committed JSON files are
  **generated data** (not hand-written tests), so materialising them under
  `tests_dir` is within this item's builder delivery; the *test module*
  `tests/test_042_golden_determinism.py` remains the test-writer's.

- **Canonical form = `json.dumps(indent=2, sort_keys=True, ensure_ascii=False)` +
  trailing `\n`, written as UTF-8 bytes.** Matches item 040's manifest house style
  (sorted keys, 2-space indent, trailing newline, `write_bytes` for exact `\n` line
  endings on Python 3.9+). `sort_keys=True` makes the on-disk key order independent
  of dict-construction order for clean diffs; `ensure_ascii=False` keeps any
  non-ASCII level names readable (none are expected in the default lumbar corpus).

- **Determinism is a per-machine, per-environment guarantee.** Byte-identical
  regeneration (AC4/AC13) holds for a fixed numpy/scipy/nibabel/Python build (the
  pinned `.venv`); goldens are pinned to the same environment item 040's fixtures
  were generated under. A dependency upgrade that legitimately shifts a feature
  float is an *intentional* change handled by the documented one-command update
  path (AC12) — exactly the "deliberate, reviewable refresh" the queue asks for.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `segqc.report.serialize_report(verdict, case_id, config, features=…, findings=…)
  -> dict` (validates against `report_schema_v0.json`; top-level keys per the table
  above); `segqc.synth.regression.loaded_seg_image(case, corpus_dir) ->
  nib.Nifti1Image`; `segqc.pipeline.run_qc(seg_img, config, *, base_reasons) ->
  (CaseResult, features_block)` with `CaseResult.findings` (each `.to_dict()`) and
  `.verdict`; `segqc.empty.check_empty(seg_img, config) -> CheckResult` with
  `.is_empty` / `.reasons`; `segqc.verdict.Reason` / `Severity.PASS` / `.FAIL`;
  `segqc.config.bundled_default_config()` with `.schema_version`;
  `segqc.synth.corpus.load_manifest` / `CORPUS_DIR`; the report-schema resource
  `importlib.resources.files(segqc).joinpath("report_schema_v0.json")`. If any
  diverged, the builder/validator hands back.

## Implementation Steps

Intended code path: new `src/segqc/synth/golden.py` + an additive re-export in
`src/segqc/synth/__init__.py`, and the committed data under
`tests/corpus/golden/`. No edits to any report/pipeline/CLI/corpus/regression/
operator/rule module.

1. **Create `src/segqc/synth/golden.py`** importing `argparse`, `copy`, `json`,
   `pathlib`; `bundled_default_config` from `segqc.config`; `check_empty` from
   `segqc.empty`; `Reason`, `Severity` from `segqc.verdict`; `run_qc` from
   `segqc.pipeline`; `serialize_report` from `segqc.report`; `load_manifest`,
   `CORPUS_DIR` from `segqc.synth.corpus`; `loaded_seg_image` from
   `segqc.synth.regression`. Import from submodules (not the `segqc.synth` package)
   to avoid a circular import through `__init__`.

2. **Module constants:** `GOLDEN_DIRNAME = "golden"`, `GOLDEN_DIR = CORPUS_DIR /
   GOLDEN_DIRNAME`, `VOLATILE_POINTERS: tuple[tuple[str, ...], ...] = ()`,
   `VOLATILE_SENTINEL = "<normalised>"`. Document above `VOLATILE_POINTERS` that
   the v0 report schema carries no volatile fields, so the allow-list is empty and
   the seam exists only for forward compatibility.

3. **`build_report_for_case(case, config=None, corpus_dir=CORPUS_DIR)`** — mirror
   `cli._handle_run` steps 3–7 in-process (see the interface block): `seg_img =
   loaded_seg_image(case, corpus_dir)`; `cfg = config or
   bundled_default_config()`; `cr = check_empty(seg_img, cfg)`; build
   `base_reasons` as `Reason(msg, Severity.FAIL if cr.is_empty else Severity.PASS)`
   for each `cr.reasons`; `case_result, features = run_qc(seg_img, cfg,
   base_reasons=base_reasons)`; `findings = [f.to_dict() for f in
   case_result.findings]`; return `serialize_report(case_result.verdict,
   case["case_id"], cfg, features=features, findings=findings)`.

4. **`canonical_json(report, *, volatile_pointers=VOLATILE_POINTERS)`** —
   `deepcopy` the report; for each pointer (a tuple of nested dict keys) walk into
   the copy and, if the full path is present, set the leaf to `VOLATILE_SENTINEL`;
   return `json.dumps(copy, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`.

5. **`golden_path` / `read_golden_text` / `load_golden`** — path join;
   `Path.read_text(encoding="utf-8")` (letting a missing file raise
   `FileNotFoundError`); `json.loads` of the text.

6. **`check_case_golden(case, config=None, golden_dir=GOLDEN_DIR,
   corpus_dir=CORPUS_DIR)`** — return
   `canonical_json(build_report_for_case(case, config, corpus_dir)) ==
   read_golden_text(case["case_id"], golden_dir)`. Do **not** swallow
   `FileNotFoundError` (AC14).

7. **`write_goldens(dest=GOLDEN_DIR, config=None, corpus_dir=CORPUS_DIR)`** —
   `dest.mkdir(parents=True, exist_ok=True)`; for each `load_manifest()["cases"]`
   case, compute `canonical_json(build_report_for_case(case, config, corpus_dir))`
   and `golden_path(case_id, dest).write_bytes(text.encode("utf-8"))`; return the
   list of written paths.

8. **`main(argv=None)`** — `argparse` with `--out` defaulting to `str(GOLDEN_DIR)`;
   call `write_goldens(Path(out))`; `print(f"Wrote N goldens to {out}")`; return 0.
   Add `if __name__ == "__main__": raise SystemExit(main())`.

9. **Generate + commit the data:** run `.venv/Scripts/python -m segqc.synth.golden`
   to materialise `tests/corpus/golden/<case_id>.json` (nine files) and commit them
   alongside the module.

10. **Re-export** `GOLDEN_DIR`, `GOLDEN_DIRNAME`, `VOLATILE_POINTERS`,
    `VOLATILE_SENTINEL`, `build_report_for_case`, `canonical_json`, `golden_path`,
    `read_golden_text`, `load_golden`, `check_case_golden`, `write_goldens` from
    `src/segqc/synth/__init__.py` (additive import + `__all__` entries).

11. **Do not** edit any report/pipeline/CLI/corpus/regression/operator/rule/config
    module, and do not add a report field or bump the report schema.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_042_golden_determinism.py`, in
  the style of `tests/test_041_regression_suite.py` (`import segqc.synth`; a
  module-level `_CASES = load_manifest()["cases"]`, `_RECONSTRUCTED_CASES = [c for
  c in _CASES if c["detection"] == "reconstructed_record"]`; Group tests
  `@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["case_id"])`).
- **Schema helper:** load `report_schema_v0.json` once via
  `importlib.resources.files(segqc).joinpath("report_schema_v0.json")` and
  `jsonschema.validate` against it (AC1, AC7), mirroring `test_009`.
- **Group A (AC1–AC3):** per-case schema validation of the freshly-built report
  (AC1); fixed-field equality (AC2); `features`/`findings` presence and
  `findings == run_qc(...).findings` dicts (AC3).
- **Group B (AC4–AC5):** two-successive-runs byte equality (AC4); canonical-form
  fixed point + sorted keys (AC5).
- **Group C (AC6–AC8):** golden-stem set == committed `case_id` set (AC6); every
  golden parses + validates (AC7); golden `case_id` == filename stem (AC8).
- **Group D (AC9):** `check_case_golden(case)` is `True` against the real
  `GOLDEN_DIR` for every case (fresh == committed bytes).
- **Group E (AC10–AC11):** synthetic two-dict normalisation with an explicit
  `volatile_pointers` (AC10); `VOLATILE_POINTERS == ()` and recursive
  volatile-key-name denylist scan over each real report (AC11).
- **Group F (AC12–AC15):** `main(["--out", tmp])` → 0 + per-case byte match (AC12);
  regenerated `tmp` file == committed golden bytes (AC13); `check_case_golden` on a
  fresh empty `tmp` raises `FileNotFoundError` (AC14); `check_case_golden` on a
  `tmp` copy with a mutated golden returns `False` (AC15).
- **Group G (AC16):** for each `_RECONSTRUCTED_CASES` golden, `verdict == "pass"`
  and no `finding.rule_id` in `expected_rule_ids`.
- **Adversarial / edge cases:**
  - `canonical_json` is idempotent under a **no-op** `volatile_pointers=()` (the
    production default leaves the report untouched byte-for-byte).
  - The `mode5_remove_level` golden (case-level finding, `labels == []`) canonicals
    and validates without crashing on empty label lists.
  - A golden with reordered top-level keys (a hand-permuted copy) canonicalises to
    the same bytes as the committed golden (sorted-key robustness).
  - `write_goldens` into an already-populated directory reproduces byte-identical
    files (idempotent regeneration — the update path is safe to re-run).
  - `clean_control`'s golden has `verdict == "pass"` and `findings == []`
    (positive control's report is snapshot-locked too).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 036** — `segqc.synth.clean_gt` / `perturbation` behind the corpus the
    goldens snapshot (the mode-0 clean control and `FAILURE_MODE_NAMES`).
  - **Item 037** — `segqc.synth.component_shape` (`fragment`, `inject_islands`):
    the pipeline mode-2/3 fixtures whose reports are snapshotted.
  - **Item 038** — `segqc.synth.coverage_border_overlap` (`remove_level`,
    `crop_at_border`, `force_overlap`): the pipeline mode-5/6 fixtures and the
    **reconstructed** mode-8 fixture whose pipeline-blind report is snapshotted
    (AC16).
  - **Item 039** — `segqc.synth.identity_ordering_alignment` (`displace`,
    `relabel_swap`, `sequence_break`): the **reconstructed** mode-1/4 fixtures
    (pipeline-blind reports, AC16) and the pipeline mode-7 fixture.
  - **Item 040** — `segqc.synth.corpus`: `load_manifest`, `CORPUS_DIR`, and the
    committed corpus (`tests/corpus/manifest.json` + `fixtures/*.nii.gz`) with the
    `detection` discriminator this item branches on for AC16. Item 040's
    Assumptions reserved `tests/corpus/golden/` for this item.
  - **Item 041** — `segqc.synth.regression.loaded_seg_image` (reused verbatim to
    load each committed seg via the Stage 0 path with the mandatory explicit
    `dtype=`), and the manifest-driven parametrisation pattern this suite mirrors.
  - **Item 009 / 016 / 035** — `segqc.report.serialize_report` and
    `report_schema_v0.json` (the JSON report + schema being snapshotted, with the
    `features`/`findings` extensions).
  - **Item 010** — `segqc.cli._handle_run` (the report-construction steps this
    item mirrors in-process).
  - **Items 034 / 035** — `segqc.pipeline.run_qc`,
    `segqc.config.bundled_default_config`, `segqc.aggregate.CaseResult`,
    `segqc.verdict` (`Reason`, `Severity`, `Verdict`).
  - **Item 003 / 010** — `segqc.io.load_case` (via `loaded_seg_image`) and
    `segqc.empty.check_empty` (the Stage 1 base-reasons the CLI threads in).
- **Downstream:** none — item 042 is the **last** item in queue-004 and closes
  Stage 5. Stage 6/7 evaluation builds on the locked corpus + regression + golden
  substrate but is a separate queue.
- **Not dependencies:** nothing else in queue-004 is parallel with 042.

## Decisions & Trade-offs

Implemented as specified, with no deviations from the pinned public
interface or Implementation Steps:

- `src/segqc/synth/golden.py` was written importing `check_empty`/`Reason`/
  `Severity`/`run_qc`/`serialize_report`/`load_manifest`/`CORPUS_DIR`/
  `loaded_seg_image`/`bundled_default_config` from their concrete submodules
  (not the `segqc.synth` package), matching item 040/041's circular-import
  avoidance convention. `build_report_for_case` mirrors `cli._handle_run`
  steps 3-7 verbatim (same `Reason`/`Severity` construction from
  `check_empty`'s `CheckResult`, same `run_qc(seg_img, cfg,
  base_reasons=...)` call, same `[f.to_dict() for f in
  case_result.findings]` then `serialize_report(...)`), with `case_id` fixed
  to `case["case_id"]` per Material Decision/Assumption in the spec.
- `canonical_json` normalises `VOLATILE_POINTERS` (empty tuple by default)
  via a small pointer-walk helper (`_normalise_pointer`) that is a no-op if
  any segment of the pointer path is absent, then serializes with
  `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False) + "\n"`.
  Verified this is a byte-for-byte no-op relative to plain `json.dumps` under
  the production default `volatile_pointers=()`.
- `write_goldens`/`main` write via `Path.write_bytes` on the UTF-8-encoded
  canonical text (not `write_text`), matching item 040's line-ending
  determinism decision (`write_text(newline=...)` is 3.10+-only; this
  project targets 3.9+).
- Generated the nine committed golden files by running
  `.venv/Scripts/python -m segqc.synth.golden` once and committing the
  output verbatim (no hand edits). Verified independently: (a) no `\r` bytes
  in any golden file; (b) regenerating into a fresh temp directory via
  `write_goldens` reproduces every committed golden byte-for-byte; (c) the
  three `reconstructed_record` goldens (`mode1_displace`,
  `mode4_relabel_swap`, `mode8_force_overlap`) all have `verdict == "pass"`
  and empty `findings`, confirming the documented pipeline-blind behaviour
  (AC16) ahead of the test-writer's assertions.
- `src/segqc/synth/__init__.py` was extended additively (new import block +
  `__all__` entries for `GOLDEN_DIR`, `GOLDEN_DIRNAME`, `VOLATILE_POINTERS`,
  `VOLATILE_SENTINEL`, `build_report_for_case`, `canonical_json`,
  `check_case_golden`, `golden_path`, `load_golden`, `read_golden_text`,
  `write_goldens`) — no existing re-exports were touched.
- No edits were made to `report.py`, `pipeline.py`, `cli.py`, `corpus.py`,
  `regression.py`, or any operator/rule/extractor/config module, per the
  item's scope boundary.
