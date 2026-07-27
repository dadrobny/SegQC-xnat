# Item 102 — Validate stage 18: Failure-Mode-Specific Metric Surface

> **Created:** 2026-07-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 18 — Failure-Mode-Specific Metric Surface (G2, G7)
> **Queue:** [`../queue/queue-014.md`](../queue/queue-014.md) · Item 102
> *(fifth and last; stage-closing per `aide-create-queue`'s convention — runs
> after 098/099/100/101 are all merged)*
> **Objectives:** G2, G7 (both stage objectives — this item is the end-to-end
> demonstration that the four preceding items compose through the **CLI**, not
> just that each passes its own unit tests)
> **Suggested branch:** `aide/102-validate-stage-18-failure-mode`

---

## Description

Replay Stage 18's use cases end to end — through the shipped CLI, not the unit
suite — and close the stage's two roadmap acceptance criteria honestly, ticking
each against what was **actually exercised** and naming, in `progress.md`, every
place the measured result falls short of the criterion's wording.

Four things shipped in this stage, and each is verified at a different level
than the item that built it:

1. **Item 098** named the stray-component population (`stray_component_count`,
   `stray_component_sizes`, `stray_volume_mm3`, `stray_volume_fraction`) and
   made the fragmentation rule read it. Verified here by a full `segfacet run`
   whose written JSON report carries the fields, validates against
   `report_schema_v0.json`, and shows the fields actually isolating §6 mode 3.
2. **Item 098's G7 promise** — the fragmentation refactor is behaviour-
   preserving — was proven at the *rule* level (`run_rules` against a frozen
   snapshot). Verified here at **report** level: nine CLI `segfacet run`
   invocations, one per corpus case, whose `verdict` + `findings` equal the
   frozen pre-098 snapshot character for character.
3. **Items 099/101** built the per-mode magnitude API and the cohort-level
   run-vs-run comparison. Item 101 proved them at the API level and with CLI
   smoke tests; verified here as the **use case the stage exists for** — two
   real CLI `segfacet evaluate --per-mode` runs over the *same* cohort
   differing in exactly one injected failure mode, diffed by a real
   `segfacet compare-runs` invocation, with the attribution landing on the
   mode that actually changed while the aggregate Dice barely moves.
4. **Item 100** built the severity-ladder monotonicity / cross-mode specificity
   harness. Verified here by running it and **recording the observed numbers**
   — rung counts, severity kinds, and every mode's measured margin — into this
   spec's Decisions log and into `progress.md`, including the two modes where
   the result is weaker than the roadmap's wording suggests.

### The two honest shortfalls this item must record, not paper over

Running the item-100 harness on this tree (measured 2026-07-27, CPU venv,
~4.3 s) gives `score_harness(...).passed is True` with every one of the eight
designated metrics **monotone and strictly changing** across its own ladder —
but the roadmap's *"and is comparatively insensitive to the others"* clause is
not uniformly met, and one ladder is degenerate:

| mode | rungs | severity kind | status | measured margin |
|---|---|---|---|---|
| 1 | 5 | continuous | strict | `inf` |
| 2 | 5 | continuous | strict | `inf` |
| 3 | 5 | continuous | strict | `112.037` |
| 4 | 3 | affected-label-count | strict | `inf` |
| 5 | 4 | affected-label-count | strict | `inf` |
| 6 | 4 | affected-label-count | **coupled → mode 1** | **`0.3585`** |
| 7 | **2** | **degenerate** | strict | `inf` |
| 8 | 5 | continuous | coupled → mode 1 | `1.0386` |

- **Mode 6 does not clear the specificity bar.** `crop_at_border`'s ladder
  drives *mode 1's* metric (`unanchored_foreground_fraction`) through **2.79×**
  more of its own full swing than mode 1's own `displace` ladder does — because
  a crop rigidly translates the body (same as `displace`) while mode 1's own
  ladder is FOV-capped at ~19.8 mm on this base. `margin(6) = 0.3585 < 1.0`.
  This is a *recorded, caused, ratcheted* coupling
  (`KNOWN_CROSS_MODE_COUPLINGS`), not a silent pass — and this item's job is to
  carry that fact onto `progress.md`, not to fix it (fixing it means widening
  mode 1's base FOV so its own metric is not artificially capped, which is a
  Stage 20 concern).
- **Mode 7's ladder is degenerate (two rungs).**
  `out_of_order_label_count` is structurally capped at 1 by the label
  convention (see item 100's Description and `insights.md`, item 100), so
  "moves monotonically with injected severity" is true only in the
  absent/present sense. Declared via `severity_kind == "degenerate"`.
- **Mode 8's margin is thin but real** (`1.0386 > 1.0`): its own metric,
  `overlapping_voxel_count`, remains a clean isolator; only its cross-check
  against metric 1 is coupled, for the same rigid-translation reason.

### The CLI trap this item must not fall into

The nine committed goldens are built by `synth/golden.py::build_report_for_case`
via `run_qc(seg_img, bundled_default_config())` — **no reference attached**. The
CLI's `segfacet run`, since item 090, has reference mode **ON by default**
(bundled `verse-v1`). Verified on this tree: a default-flag run of
`mode3_inject_islands` emits 20 `bounds` findings, 25 `reference_delta`
findings, and a *reference-branch* fragmentation reason
(`"...fragmentation_index=0.998562 is below reference floor 0.9986"`), whereas
the golden has exactly one hand-set-branch finding
(`"Rogue island(s): Label 22: 1 non-dominant component(s) strictly below
island_min_voxels=50..."`). Adding `--no-reference` reproduces the golden's
`verdict` + `findings` exactly. Every report-level G7 comparison in this item
therefore runs with `--no-reference`; the schema check runs both ways.

**What this item is NOT:**

- **Not new production code.** `src/segfacet/**` is byte-identical to its
  pre-102 state. This item adds one test module and edits `progress.md`.
- **Not a fix for mode 6's coupling, mode 7's degenerate ladder, or item 101's
  `normalised_delta` saturation trap.** All three are recorded (two already in
  `insights.md`); acting on them is out of scope and belongs to Stage 20 or a
  follow-up item.
- **Not a real-data claim.** Every metric, ladder, cohort and comparison in
  Stage 18 runs on the **synthetic** corpus or on in-memory perturbed clean
  spines. Nothing here touches the pre-existing "Real automatic-segmentation
  failure corpus" verification row (Stage 16's job) or the Outcome-targets
  table, and the `progress.md` text this item writes must not imply otherwise.
- **Not Stage 19/20.** The generated feature catalogue, the golden-retirement
  decision table, and the traceability harness are separate stages.

## Acceptance Criteria

- [ ] **AC1: a full CLI `segfacet run` surfaces the item-098 stray fields.**
  `segfacet.cli.main(["run", "--scan", <base_scan>, "--seg",
  <mode3_inject_islands_seg>, "--out", <tmp>])` returns `0` and writes
  `<tmp>/segfacet_report.json` in which **every** entry of
  `features.per_label` carries a `components` block containing all four keys
  `stray_component_count`, `stray_component_sizes`, `stray_volume_mm3`,
  `stray_volume_fraction`.

- [ ] **AC2: the stray fields isolate §6 mode 3 end to end.** In that same
  written report, label `22` has `stray_component_count == 1`,
  `stray_component_sizes == [27]`, `stray_volume_mm3 == 27.0` and
  `0.0 < stray_volume_fraction < 0.01`; labels `20`, `21`, `23`, `24` each have
  `stray_component_count == 0`, `stray_component_sizes == []`,
  `stray_volume_mm3 == 0.0` and `stray_volume_fraction == 0.0`.

- [ ] **AC3: the end-to-end report validates against the bundled schema in both
  reference modes.** The JSON written by the default-flag run **and** the JSON
  written by a `--no-reference` run of the same case both pass
  `jsonschema.validate` against the bundled
  `src/segfacet/report_schema_v0.json` (loaded via `importlib.resources`, not a
  hardcoded path).

- [ ] **AC4: the complement invariant holds at report level.** For every label
  of both reports written in AC3,
  `stray_volume_fraction + largest_component_fraction == 1.0` within `1e-12`
  absolute tolerance.

- [ ] **AC5: G7 at report level — nine corpus cases, verdicts and findings
  unchanged from pre-098.** For each of the nine `tests/corpus` cases, a CLI
  `main(["run", "--no-reference", "--scan", <base_scan>, "--seg",
  <case seg fixture>, "--out", <tmp/case_id>])` returns `0`, and the written
  report's `verdict` string plus its `findings` array — length, order, and each
  finding's `rule_id`, `severity`, sorted `labels`, and character-for-character
  `reason` — equal the frozen pre-098 snapshot
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` in
  `tests/test_098_stray_components.py` (imported, not re-transcribed).

- [ ] **AC6: `--no-reference` is load-bearing for AC5, and the test says so.**
  A companion test asserts that the **default-flag** run of
  `mode3_inject_islands` does *not* equal the pre-098 snapshot — specifically
  that its `findings` include at least one `rule_id == "reference_delta"` and
  at least one `rule_id == "bounds"`, and that its single `fragmentation`
  finding's `reason` differs from the snapshot's — so a future reader cannot
  "simplify" AC5 by dropping the flag and get a spurious failure.

- [ ] **AC7: two real `segfacet evaluate --per-mode` CLI runs over the same
  cohort each write an eight-entry per-mode block.** Two invocations
  `main(["evaluate", "--cohort", <manifest>, "--out", <dir>, "--per-mode",
  "--run-id", <id>, ...])` — over two manifests with identical `case_id`s and
  identical GT paths, differing only in the `candidate` files — each return `0`
  and each write an `eval_report.json` whose `per_mode_magnitude` block lists
  exactly eight entries, in ascending `failure_mode` order `1..8`, each with a
  non-`None` mean, and whose `run_id` equals the `--run-id` passed.

- [ ] **AC8: `segfacet compare-runs` produces a schema-valid comparison from
  those two written reports.** `main(["compare-runs", "--run-a", <A>,
  "--run-b", <B>, "--out", <D>])` returns `0`, writes
  `<D>/per_mode_comparison.json` validating against the bundled
  `src/segfacet/eval/per_mode_comparison_schema_v0.json`, writes a non-empty
  `<D>/per_mode_comparison.txt`, and prints exactly one stdout line naming the
  attributed mode.

- [ ] **AC9: the per-mode attribution lands on the mode that actually changed.**
  With both runs' candidates carrying the *same* background departure
  (`displace(target_label=22, displacement_mm=8.0)` then
  `fragment(target_label=20, n_pieces=3)` applied to `build_clean_spine()`'s
  `seg_img`) and run A additionally carrying
  `inject_islands(target_label=24, n_islands=3, island_voxels=27)`, the written
  comparison has `comparison.attributed_mode == 3`,
  `comparison.attributed_metric_name == "rogue_island_count"`, and mode 3's
  entry has `value_a == 3.0`, `value_b == 0.0`, `delta == -3.0`,
  `normalised_delta == -1.0`, `worsened is False`.

- [ ] **AC10: no mode the change did not touch is implicated.** In that same
  comparison, modes `4`, `5`, `6`, `7`, `8` each have `delta == 0.0` and
  `normalised_delta == 0.0`, and mode 1's `abs(normalised_delta) < 0.05` (the
  measured value on this construction is `0.0109`) — i.e. mode 3's signal
  exceeds every other mode's by more than an order of magnitude.

- [ ] **AC11: the aggregate Dice does not attribute what the per-mode delta
  does.** In that same comparison, `abs(comparison.mean_dice_delta) < 0.01`
  (measured `0.00043`) while mode 3's `abs(normalised_delta) == 1.0` — the
  aggregate move is at least two orders of magnitude smaller than the per-mode
  signal. This is the stage's thesis, asserted on a real CLI artifact.

- [ ] **AC12: the rendered human comparison names the implicated mode in
  words.** `<D>/per_mode_comparison.txt` contains the literal string
  `FAILURE_MODE_NAMES[3]` (`"disconnected components / rogue islands"`) and the
  metric name `rogue_island_count` on its attribution line, and lists all eight
  `FAILURE_MODE_NAMES` values in its per-mode table.

- [ ] **AC13: the comparison fixture is off-baseline on the confounding modes,
  so AC9 is not a saturation artefact.** In the written comparison, modes `1`
  and `2` each have `value_a != baseline` **and** `value_b != baseline` — the
  construction deliberately avoids the `normalised_delta = ±1.0` saturation
  trap recorded in `insights.md` (item 101, 2026-07-27), which fires whenever a
  compared mode's run-A value sits exactly on its baseline. Mode 3 is the only
  entry with `abs(normalised_delta) == 1.0`.

- [ ] **AC14: the item-100 harness passes, with monotone, strictly-changing
  metrics for all eight modes.** `score_harness(run_severity_harness())`
  returns `passed is True`, and for every mode `1..8` the corresponding
  `per_ladder[m]` has `monotone is True`, `strictly_changed is True` and
  `failures == ()`.

- [ ] **AC15: the observed ladder shapes match the recorded ones.** The
  harness's per-mode rung counts are exactly
  `{1: 5, 2: 5, 3: 5, 4: 3, 5: 4, 6: 4, 7: 2, 8: 5}` and severity kinds exactly
  `{1: "continuous", 2: "continuous", 3: "continuous",
  4: "affected-label-count", 5: "affected-label-count",
  6: "affected-label-count", 7: "degenerate", 8: "continuous"}`.

- [ ] **AC16: every mode's observed margin is recorded and satisfies the frozen
  ratchet.** For each mode `1..8`, `per_ladder[m].margin >=
  RECORDED_MARGINS[m] * 0.95` (`math.inf` compared as `math.inf`), and the
  observed values — `1: inf, 2: inf, 3: 112.037, 4: inf, 5: inf, 6: 0.3585,
  7: inf, 8: 1.0386` — are written verbatim into this item's Decisions log.

- [ ] **AC17: the two shortfall modes are asserted as such, not as passes.**
  `per_ladder[6].status == "coupled"` with `coupled_modes == (1,)` and
  `margin < 1.0`; `per_ladder[8].status == "coupled"` with `coupled_modes ==
  (1,)` and `margin > 1.0`; modes `1, 2, 3, 4, 5, 7` all have
  `status == "strict"`; and `SEVERITY_LADDERS[7].severity_kind ==
  "degenerate"` with a non-empty `rationale`.

- [ ] **AC18: `progress.md`'s Stage 18 G2 acceptance box is ticked with an
  honest qualification.** The box *"Each §6 mode has ≥1 named metric moving
  monotonically with injected severity of that mode, and comparatively
  insensitive to the others (G2)"* is ticked, annotated in ≤5 lines that state,
  in this order: (a) all eight modes have a named metric that is monotone and
  strictly changing across its own ladder (item 100, replayed by item 102);
  (b) seven of eight ladders clear the strict-specificity bar (`margin > 1.0`)
  while **mode 6** does not — measured margin `0.3585`, its ladder driving
  mode 1's `unanchored_foreground_fraction` `2.79×` harder than mode 1's own
  FOV-capped ladder, recorded in `KNOWN_CROSS_MODE_COUPLINGS`; (c) **mode 7**
  carries a declared two-rung degenerate ladder (metric structurally capped at
  1 by the label convention); (d) all of it is measured on synthetic ladders
  only.

- [ ] **AC19: `progress.md`'s Stage 18 G7 acceptance box is ticked, evidenced at
  report level.** The box *"The fragmentation rule's behaviour is unchanged by
  the refactor (G7)"* is ticked with a one-line pointer to AC5 — nine CLI
  `segfacet run --no-reference` invocations whose `verdict` + `findings` equal
  the frozen pre-098 snapshot — explicitly noting this is *report*-level
  evidence, above item 098's rule-level regression.

- [ ] **AC20: Stage 18's status flips to ✅ in both places.** The Stage 18
  section heading changes `— 🚧` → `— ✅`, its item-102 deliverable bullet
  changes `📋` → `✅`, and the Stage summary table's row `18` changes `🚧` →
  `✅`.

- [ ] **AC21: a new Environment-Gated Capability Verification row is added,
  `❓ Unverified`.** A row **"Real segmentation-tool run-vs-run per-mode
  comparison"** — Package/Tool/Data: two real runs of a real segmenter over the
  same cohort (e.g. a post-processing step on vs. off), external tool + data;
  Introduced by: Stage 18 *(Items 101, 102)*; Status: `❓ Unverified`; Evidence:
  one line stating that the comparison has only ever been exercised on the
  synthetic corpus and on in-memory perturbed clean spines, that no two real
  segmenter runs exist in this repo, and that this row is **narrower** than the
  "Real automatic-segmentation failure corpus" row (which is Stage 16's
  per-mode *sensitivity* scope, not this row's run-vs-run *attribution* scope).

- [ ] **AC22: Stage 18 does not close, weaken, or appear to close the real-
  failure-corpus row.** The "Real automatic-segmentation failure corpus" row's
  Status remains `❓ Unverified` and continues to name Stage 16 as its closer;
  the two Outcome-targets rows for G2/G7 are byte-identical to their pre-102
  state; and no sentence added to `progress.md` by this item asserts real-data
  coverage for any Stage 18 metric.

- [ ] **AC23: the CI-observation sub-claim is recorded at exactly its true
  strength.** This item's Decisions log records whether a live CI run was
  observed green on `main` for the merged Stage 18 tree, naming the commits
  covered and — critically — the **observation channel** (unauthenticated
  GitHub Actions REST API: `/actions/runs`, `/actions/jobs`,
  `/check-runs/{id}/annotations` — job/check conclusions, **not** raw pytest
  logs). If re-observation is impossible at execution time, that is recorded
  honestly instead; in neither case is a green CI run asserted without a named
  channel.

- [ ] **AC24: the scope fence holds — no production code changed.** Every file
  under `src/segfacet/` is byte-identical to its pre-102 state (asserted via a
  combined SHA-256 over the tree, joining relative paths with
  `Path.relative_to(base).as_posix()` — **never** `str(Path)`, per the item-099
  and item-101 Windows-CI hotfixes recorded in `insights.md`), and
  `docs/aide/roadmap.md` and `docs/aide/vision.md` are untouched.

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`). Defaults taken, and
the interfaces each pins:

- **This item adds tests + `progress.md` edits only, no production code.**
  Item 097 (the analogous Stage 17 closer) *did* end up changing
  `human_report.py` because one of its ACs could not otherwise pass. Every AC
  here was checked against the merged tree before this spec was written (see
  Validation), and all of them pass with the code as it stands — so any
  production-code change the builder finds necessary is a **signal to hand
  back**, not a licence to widen scope. AC24 makes that mechanical.

- **The nine-case G7 replay uses `--no-reference`.** Pinned interface: the
  goldens come from `run_qc(seg_img, bundled_default_config())` with no
  reference (`synth/golden.py:84-108`) while `segfacet run` defaults reference
  mode ON since item 090 (`cli.py`'s `--reference`/`--no-reference` pair).
  Verified empirically on this tree: `--no-reference` reproduces
  `mode3_inject_islands`'s golden `verdict` + `findings` exactly, the default
  does not. If the CLI's reference default ever flips, AC5/AC6 are the tests
  that will say so.

- **AC5 compares `verdict` + `findings` only, not the whole report.** The CLI
  derives `case_id` from the `--seg` filename while the golden carries the
  corpus `case_id`, and the CLI's `features` block legitimately grew by four
  keys in item 098. Whole-file equality would therefore be wrong; the G7
  claim is precisely about rule *behaviour*, which is exactly `verdict` +
  `findings`.

- **The run-vs-run fixture is built in-memory from `build_clean_spine()` +
  registered perturbation operators, not from the committed corpus fixtures.**
  The committed `mode3_inject_islands` fixture cannot demonstrate attribution:
  stripping its islands reconstructs the candidate to *exactly* GT, so modes 1,
  2 and 3 all saturate to `abs(normalised_delta) == 1.0` simultaneously and
  item 101's lowest-mode tie-break attributes to mode **1** — the failure item
  101's builder flagged and `insights.md` records. The composite construction
  in AC9 (a shared `displace` + `fragment` background departure that both runs
  keep, plus islands only in run A) keeps modes 1 and 2 strictly off baseline
  and yields a clean mode-3 attribution. **Measured on this tree, 2026-07-27**
  (see Validation for the exact numbers): `attributed_mode == 3`,
  mode 3 `normalised_delta == -1.0`, mode 1 `-0.0109`, mode 2 `0.0`, modes 4-8
  `0.0`, `mean_dice_delta == 0.00043`.

- **`build_clean_spine()` returns a `CleanSpine` dataclass, not an image** —
  the perturbation operators take `spine.seg_img`. Pinned because it is an easy
  and silent mistake (`AttributeError: 'CleanSpine' object has no attribute
  'dataobj'`).

- **Stage 18 introduces no *package*- or *tool*-gated capability**, so no
  `aide.toml` `[validation]` profile is added and no
  `aide env --profile <name>` check applies. The one genuinely gated thing the
  stage introduces is **data**-gated — two real segmenter runs over one cohort
  — which is why AC21 adds a verification row rather than a profile, mirroring
  item 097's `SEGFACET_SPINEPS_FIXTURE` reasoning (data absence, not a missing
  pip package). No new environment variable is introduced either: unlike item
  097, no test here is *gated* on the real data — the row records an
  unexercised real-world path, not a skipping test.

- **The G2 acceptance box is ticked *with* its qualification rather than left
  open.** Stage 18's planned work shipped and is verified; the shortfall is in
  the *measured outcome* for one of eight modes, and this tracker's own
  "Two kinds of done" rule (`progress.md:58-77`) says a stage's ✅ is a claim
  about code, with unmet outcomes recorded rather than blocking the stage.
  Objective **G2 stays 🚧** regardless (it is already 🚧 pending Stage 16's real
  corpus), so nothing is over-claimed by ticking the box with the shortfall
  written on the same line.

- **Mode 6's coupling and mode 7's degenerate ladder are recorded, not fixed.**
  Mode 6's margin is an artefact of mode 1's ladder being FOV-capped on the
  5-level base, so the fix is a wider base for the mode-1 ladder — a change to
  item 100's registry, i.e. new stage work (Stage 20 territory), not stage
  validation. Mode 7 is already logged in `insights.md` (item 100).

- **Dependencies 098, 099, 100, 101 are all ✅ merged before this item starts.**
  This is the explicit stage-closing item; it has no meaning earlier.

## Implementation Steps

No changes under `source_dir = src/segfacet`. The work is one new test module
plus `docs/aide/progress.md`.

1. **New test module `tests/test_102_stage18_validation.py`.** Structure it in
   four blocks matching the four things being replayed, with module-scoped
   fixtures so the expensive artifacts are built once:
   - **Block A (AC1-AC4, AC6)** — CLI `run` on `mode3_inject_islands`, default
     flags and `--no-reference`. Use
     `segfacet.cli.main([...])` directly (the style of
     `tests/test_035_cli_e2e.py`), `tmp_path_factory` for outputs, and resolve
     the corpus fixtures relative to the test file (never an absolute path —
     see AC24's note and `insights.md`, item 099).
   - **Block B (AC5)** — parametrise over the nine `case_id`s read from
     `tests/corpus/manifest.json`; `from tests.test_098_stray_components import
     _PRE_098_GOLDEN_VERDICT_AND_FINDINGS` (or the equivalent import path this
     suite already uses for cross-module test imports) rather than
     re-transcribing the snapshot — a second copy would drift.
   - **Block C (AC7-AC13)** — build the two candidate label maps in a
     module-scoped fixture:
     ```
     spine = build_clean_spine(levels=("L1","L2","L3","L4","L5"),
                               spacing=(1.0,1.0,1.0), curve_amplitude_mm=6.0)
     base  = spine.seg_img
     common = [("displace",  {"target_label": 22, "displacement_mm": 8.0}),
               ("fragment",  {"target_label": 20, "n_pieces": 3})]
     cand_a = apply(base, common + [("inject_islands",
                     {"target_label": 24, "n_islands": 3, "island_voxels": 27})])
     cand_b = apply(base, common)
     ```
     where `apply` chains `get_perturbation(name)(**kw).apply(img, SEED).labelmap`
     (the same shape as `eval/severity_ladder.py::_apply_steps`). Write
     `gt`/`cand_a`/`cand_b` NIfTIs under `tmp_path`, write two cohort manifests
     (`{"manifest_version": 1, "cases": [{case_id, gt, candidate, expected}]}`,
     paths **relative to the manifest**), then drive
     `cli.main(["evaluate", ...])` twice and `cli.main(["compare-runs", ...])`
     once. Follow `tests/test_101_compare_runs_cli.py`'s `_write_manifest` /
     `_run_evaluate` helpers (pass `--build-date` and `--cohort-id` so the
     provenance block is deterministic). Note the JSON nesting: the eight
     deltas live at `doc["comparison"]["per_mode"]`, with `run_a`/`run_b`/
     `schema_version` as siblings of `comparison`.
   - **Block D (AC14-AC17)** — one module-scoped
     `score_harness(run_severity_harness())` (~4.3 s) shared by all four tests;
     import `RECORDED_MARGINS`, `SEVERITY_LADDERS` and `COUPLING_THRESHOLD`
     from `segfacet.eval.severity_ladder`.
   - **AC24** — the scope-fence hash, modelled on items 099/101's
     `_combined_hash` **after** the `3e218cd` fix: `hashlib.sha256` over
     `sorted(base.rglob("*.py")) + sorted(base.rglob("*.json"))`, feeding
     `p.relative_to(base).as_posix().encode()` then `p.read_bytes()`.
     `src/segfacet/**/*.py` and `**/*.json` are already pinned `text eol=lf` in
     `.gitattributes` by commit `694d955`, so no `.gitattributes` change is
     needed — **confirm this before adding the test**, and if any new path is
     hashed that is not covered, pin it.

2. **`docs/aide/progress.md`** — the only non-test edit:
   - Stage 18 section heading `— 🚧` → `— ✅` (AC20).
   - Item 102's deliverable bullet `📋` → `✅` (AC20).
   - Stage summary table row `18` `🚧` → `✅` (AC20).
   - Tick both Stage 18 acceptance boxes with the annotations AC18/AC19
     specify.
   - Append the new Environment-Gated Capability Verification row (AC21),
     keeping the **Evidence / references** column to one line per that table's
     own stated rule.
   - **Do not** touch the "Real automatic-segmentation failure corpus" row's
     Status, the Outcome-targets table, or the Objective-coverage table
     (AC22) — G2/G7 stay 🚧, gated on Stage 16.

3. **Do NOT touch** `src/segfacet/**`, `tests/corpus/**`,
   `docs/aide/roadmap.md`, `docs/aide/vision.md`, or any existing test module.

## Testing Strategy

- **Framework:** `pytest`, single new module
  `tests/test_102_stage18_validation.py`. One focused test per AC; AC5 is
  parametrised over the nine corpus cases (nine test ids, not one loop, so a
  single regressing case names itself).

- **Cost control:** three module-scoped fixtures — the CLI `run` outputs
  (Block A), the evaluate/compare artifacts (Block C), and the harness verdict
  (Block D, ~4.3 s). Without them the module re-runs the harness and two full
  cohort evaluations per test.

- **Adversarial / edge cases:**
  - **The `--no-reference` inversion (AC6)** is itself the primary adversarial
    case: it proves the AC5 comparison is configuration-sensitive and would
    have caught a silent flip of the CLI's reference default.
  - **Mis-attribution control:** re-run `compare_runs` with `--run-a` and
    `--run-b` swapped; the attributed mode must still be `3` and mode 3's
    `normalised_delta` must flip sign to `+1.0` with `worsened is True`
    (islands *appearing* is a regression). Catches a direction-of-comparison
    bug that AC9 alone would not.
  - **Self-comparison:** `compare-runs --run-a A --run-b A` must produce an
    all-zero comparison with `attributed_mode is None` and a `.txt` that names
    **no** failure mode (item 101's `render_run_comparison` suppresses the
    table in the degenerate case — assert that behaviour holds through the
    CLI, not just the API).
  - **Mismatched cohorts:** `compare-runs` over a report built from a
    *different* `case_id` set exits `1` with an `Error:` line on stderr and
    writes nothing — re-confirmed at CLI level as part of the stage replay.
  - **Determinism:** running the whole Block C pipeline twice into two fresh
    directories in one session yields byte-identical
    `per_mode_comparison.json` files (`dest1 == dest2`), and two
    `run_severity_harness()` calls yield equal `to_dict()`s.
  - **No-mutation:** the two cohort manifests and their fixture NIfTIs are
    unchanged (by SHA-256) after both `evaluate` runs and the `compare-runs`
    run.
  - **Empty/degenerate report input:** a `compare-runs` against an
    `eval_report.json` written *without* `--per-mode` exits `1`, not a
    traceback — the most likely real-world operator error for this new
    subcommand.

- **Existing tests to reconcile** (grep sweep — all expected to stay green
  **unmodified**; any edit to them is a red flag for the validator, since this
  item changes no production behaviour):
  - `tests/test_098_stray_components.py` — its
    `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` and
    `_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS` snapshots are **imported** by
    this item's AC5, not copied; confirm the names are importable (module-level
    constants, not fixtures) and that importing the module has no side effects.
  - `tests/test_042_golden_determinism.py` — the nine goldens' owner; AC5
    approaches the same claim from the CLI side and must not require any change
    here.
  - `tests/test_099_per_mode_metrics.py`,
    `tests/test_100_severity_ladder.py`,
    `tests/test_101_per_mode_cohort.py`,
    `tests/test_101_compare_runs_cli.py` — each carries a `_PRE_0NN_HASHES`
    scope-fence over `src/segfacet/**`. Because AC24 asserts `src/segfacet/**`
    is byte-identical to its pre-102 state, **all** of those hashes must
    continue to match; if any fails, a production file was touched and this
    item is out of scope. (Note the standing framework issue in `insights.md`
    about these fences breaking when a later item is *legitimately* authorised
    to edit a pinned file — that is not the case here, which is precisely why
    they are a useful cross-check for this item.)
  - `tests/test_035_cli_e2e.py`, `tests/test_035_report_integration.py` — the
    CLI-invocation style this module should follow; no changes expected.

## Validation

The whole point of this item is **observed** behaviour, so the validator must
execute the replay rather than only re-run the suite. Every command below was
actually run against the merged tree on 2026-07-27 (Linux, CPU venv, no
optional dependencies) while authoring this spec; the expected outputs are the
observed ones, not predictions.

**1. Stray fields + G7 at report level.**

```
.venv/bin/python -m segfacet.cli run --no-reference --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/mode3_inject_islands_seg.nii.gz --out <tmp>/noref
```

Observed: `<tmp>/noref/segfacet_report.json` has `verdict ==
"flagged-for-review"` and exactly one finding —
`fragmentation / flagged-for-review / [22] / "Rogue island(s): Label 22: 1
non-dominant component(s) strictly below island_min_voxels=50. Tiny island
sizes: [27]. component_count=2, component_sizes=[18750, 27],
fragmentation_index=0.9985620706183096"` — **identical** to
`tests/corpus/golden/mode3_inject_islands.json`. Label 22's `components` block
reads `stray_component_count: 1`, `stray_component_sizes: [27]`,
`stray_volume_mm3: 27.0`, `stray_volume_fraction: 0.001437929381690406`.
Dropping `--no-reference` on the same case yields 20 `bounds` + 25
`reference_delta` findings and a different `fragmentation` reason — the trap
AC6 pins.

**2. Run-vs-run per-mode attribution through the CLI.** Build the composite
candidates per the Implementation Steps, then:

```
.venv/bin/python -m segfacet.cli evaluate --cohort <tmp>/cohort_a.json --out <tmp>/runA --per-mode --run-id runA --build-date 2026-07-27 --cohort-id stage18
```
```
.venv/bin/python -m segfacet.cli evaluate --cohort <tmp>/cohort_b.json --out <tmp>/runB --per-mode --run-id runB --build-date 2026-07-27 --cohort-id stage18
```
```
.venv/bin/python -m segfacet.cli compare-runs --run-a <tmp>/runA/eval_report.json --run-b <tmp>/runB/eval_report.json --out <tmp>/compare
```

Observed stdout from `compare-runs`:

```
compare-runs 'runA' vs 'runB': attributed to mode 3 (disconnected components / rogue islands, rogue_island_count), normalised_delta=-1.000
```

Observed `<tmp>/compare/per_mode_comparison.json` (`comparison.per_mode`):

| mode | metric | value_a | value_b | delta | normalised_delta |
|---|---|---|---|---|---|
| 1 | `unanchored_foreground_fraction` | 0.079264 | 0.0784 | -0.000864 | **-0.0109** |
| 2 | `min_dominant_component_fraction` | 0.347826 | 0.347826 | 0.0 | 0.0 |
| 3 | `rogue_island_count` | 3.0 | 0.0 | -3.0 | **-1.0** |
| 4-8 | — | 0.0 | 0.0 | 0.0 | 0.0 |

with `mean_dice_a = 0.91284`, `mean_dice_b = 0.91327`, **`mean_dice_delta =
0.00043`**. Confirm by eye in `per_mode_comparison.txt` that all eight modes
appear by name, that the attribution line names mode 3 in words, and that the
aggregate Dice line sits beside it and is visibly tiny — that one screen is the
stage's thesis.

**3. The monotonicity / specificity harness.**

```
.venv/bin/python -c "from segfacet.eval.severity_ladder import run_severity_harness, score_harness; v = score_harness(run_severity_harness()); print(v.passed); print(v.summary() if hasattr(v, 'summary') else v)"
```

Observed: `passed True`, ~4.3 s, with the per-mode rung counts, severity kinds,
statuses and margins exactly as tabulated in the Description. **Record the
observed margins in the Decisions log** and carry the mode-6 / mode-7
shortfalls into `progress.md` per AC18.

**No `[validation]` profile is required** — everything above runs on the plain
CPU venv with no optional dependency, so nothing here may be recorded
`❓ Unverified` for environment reasons. If the venv is missing, run
`python .aide/scripts/aide.py env --bootstrap` rather than downgrading a check.

**CI observation.** Unlike item 097 — which had no channel to observe CI and
had to leave its dual-numpy-major claim honestly unverified — a live GitHub
Actions run on `main` was observed green for this stage's merged tree during
this session, covering item 101's merge plus hotfixes `694d955` (LF pinning)
and `3e218cd` (OS-native path-separator fix in the combined-hash scope-fence
tests). That observation was made through the **unauthenticated GitHub Actions
REST API** (`/actions/runs`, `/actions/jobs`,
`/check-runs/{id}/annotations`) — i.e. job and check-run conclusions plus
failure annotations, **not** raw pytest logs. Record it at exactly that
strength (AC23); do not upgrade it to "the suite was observed passing test by
test", and do not extend it to any commit the run did not cover.

## Dependencies

- **Item 098** (first-class stray-component fields, the updated
  `report_schema_v0.json`, the nine regenerated goldens, and the frozen
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` snapshot AC5 imports) — ✅.
- **Item 099** (`eval/per_mode.py` — the eight named magnitude metrics and
  `PER_MODE_METRIC_SPECS`, which both the harness and the cohort report read) —
  ✅.
- **Item 100** (`eval/severity_ladder.py` — `run_severity_harness`,
  `score_harness`, `SEVERITY_LADDERS`, `KNOWN_CROSS_MODE_COUPLINGS`,
  `RECORDED_MARGINS`) — ✅.
- **Item 101** (`eval/per_mode_cohort.py`, the `per_mode_magnitude` report
  block, `per_mode_comparison_schema_v0.json`, and the CLI surface
  `evaluate --per-mode` / `compare-runs`) — ✅.

**Downstream:** Stage 19's golden-file decision table inherits this item's
report-level G7 evidence as one input to the "keep or retire" call on the nine
whole-record goldens; Stage 20's traceability/specificity harness inherits the
mode-6 coupling and mode-7 degenerate ladder recorded here as its starting
backlog. Neither blocks this item.

## Decisions & Trade-offs

**Scope fence held.** Ran the full replay per the spec's Implementation Steps
and Validation section on this checkout (Linux, CPU venv, no optional
dependencies, 2026-07-27). All 24 acceptance criteria pass as specified,
including AC24's combined-hash scope-fence over `src/segfacet/**`; no
production file needed a change. The only edits made were the new test module
`tests/test_102_stage18_validation.py` (already committed by the test-writer)
and this item's `docs/aide/progress.md` section (Stage 18 heading, item-102
deliverable bullet, stage-summary table row, both acceptance boxes, and the
new Environment-Gated Capability Verification row). This confirms AC24's
scope-fence assertion and the Assumptions section's expectation that any
production-code need would be a hand-back signal — none arose.

**Observed harness margins (item 100's `run_severity_harness()` replayed by
this item, `score_harness(...).passed is True`), transcribed verbatim from the
Description/AC16 into this log per AC16's requirement:**

| mode | rungs | severity kind | status | measured margin |
|---|---|---|---|---|
| 1 | 5 | continuous | strict | `inf` |
| 2 | 5 | continuous | strict | `inf` |
| 3 | 5 | continuous | strict | `112.037` |
| 4 | 3 | affected-label-count | strict | `inf` |
| 5 | 4 | affected-label-count | strict | `inf` |
| 6 | 4 | affected-label-count | **coupled → mode 1** | **`0.3585`** |
| 7 | **2** | **degenerate** | strict | `inf` |
| 8 | 5 | continuous | coupled → mode 1 | `1.0386` |

Mode 6 does not clear the specificity bar (`margin(6) = 0.3585 < 1.0`):
`crop_at_border`'s ladder drives mode 1's own metric
(`unanchored_foreground_fraction`) through 2.79× more of its own full swing
than mode 1's own `displace` ladder does, because a crop rigidly translates
the body the same way `displace` does while mode 1's own ladder is FOV-capped
at ~19.8 mm on this base — a recorded, caused, ratcheted coupling
(`KNOWN_CROSS_MODE_COUPLINGS`), not a silent pass. Mode 7's ladder is
degenerate (two rungs): `out_of_order_label_count` is structurally capped at 1
by the label convention, so "moves monotonically with injected severity" is
true only in the absent/present sense (`severity_kind == "degenerate"`). Mode
8's margin is thin but real (`1.0386 > 1.0`): its own metric
(`overlapping_voxel_count`) remains a clean isolator; only its cross-check
against metric 1 is coupled, for the same rigid-translation reason. Neither
shortfall was fixed here — both are recorded in `progress.md`'s G2 acceptance
annotation (AC18) and in `insights.md` (mode 7, from item 100), matching this
item's explicit non-goal.

**Run-vs-run attribution replay (AC7-AC13), measured on this tree:**
`compare-runs` attributes to `attributed_mode == 3`
(`rogue_island_count`), mode 3 `normalised_delta == -1.0`, mode 1
`-0.0109`, mode 2 `0.0`, modes 4-8 `0.0`, `mean_dice_delta == 0.00043` — all
matching the spec's Validation section exactly.

**Discrepancies found vs. the spec's pre-measured expectations: none.** Every
numeric value in AC1-AC17/AC24 (stray-component fields, the nine-case G7
report-level replay, the run-vs-run attribution numbers, the harness rung
counts/severity kinds/statuses/margins) reproduced exactly as the spec's
Validation section recorded them, on the same Linux/CPU/no-optional-deps
configuration the spec's author used. This is consistent with the spec having
been written directly against the merged tree rather than drafted ahead of
verification.

**CI observation (AC23).** No live re-observation of GitHub Actions was made
during this execution session (no `gh` CLI / network access to the GitHub
Actions REST API available in this environment, matching item 097's
precedent). This item therefore does **not** independently confirm the spec's
own claim (a green run on `main` observed via the unauthenticated GitHub
Actions REST API — `/actions/runs`, `/actions/jobs`,
`/check-runs/{id}/annotations` — covering item 101's merge plus hotfixes
`694d955` and `3e218cd`, made during the spec-authoring session). That claim
stands as recorded in the spec's Validation section, at the strength stated
there (job/check-run conclusions via the REST API, not raw pytest logs); this
item adds no new CI observation of its own, and does not upgrade the prior
claim's strength.
