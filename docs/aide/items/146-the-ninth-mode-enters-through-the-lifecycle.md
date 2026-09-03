# Item 146 — The ninth mode enters through the lifecycle, and the first `proposed` entry

> **Created:** 2026-09-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 146
> **Objectives:** G2 (detect catalogued failure modes), G7 (measured on a
> corrected corpus), G8 (generated artifacts are conformance reports)
> **Suggested branch:** `aide/146-the-ninth-mode-enters-through`

---

## Description

Stage 30 D3. Items 144 and 145 built the failure-mode specification
(`src/segfacet/failure_modes.py`) and entered vision §6's eight hypothesised
modes into it. This item is the **first exercise of the lifecycle those two
established**: a mode that is not in vision §6's numbered list enters the
specification through the schema, acquires its rules, and derives its status
from live state — the test of vision §6's claim that "a mode can be added
without everything being rebuilt".

Three deliverables, one seam:

1. **The ninth mode — implausible tissue under a label.** Soft tissue or air,
   metal or implant, or a degenerate uniform region under a vertebra label, on
   CT. `observability = "needs-paired-scan"` with the modality stated in the
   definition. The `intensity` and `intensity_reference_delta` rules'
   `RuleModeDeclaration`s move from **mode-less** (item 137's disposition,
   taken because §6 named no tissue-plausibility mode) to **declaring mode 9**.
   `tests/corpus/intensity/manifest.json`'s four cases gain the `failure_mode`
   and expected-firing fields the geometric manifest already carries. The mode
   is expected to derive `validated`, never a hand-set value.

2. **The intensity harness that has never existed.** Driving those four cases
   needs the intensity sibling of `synth/regression.py::pipeline_findings`
   (`insights.md`, item 139, 2026-09-03). It is built **in
   `synth/regression.py`**, where the geometric one lives, so the second
   committed corpus finally has a public harness, and `measured_firing` gains
   an intensity dispatch routed through it.

3. **The catalogue's first `proposed` entry — collapsed or duplicated label
   set.** The silent case where two labels share an exact centroid, Stage 3
   degrades, every `stage3`-reading rule short-circuits and no finding of any
   kind is raised (carried defect, item 129, 2026-08-31). No rules, no corpus
   cases, one hypothesised candidate feature. It exists so the conformance
   report shows a listed, unimplemented mode for the first time — and so the
   rendering has to render one legibly rather than as a bare heading with
   nothing under it.

**What this item is NOT.** It writes **no new rule** — the detector for the
collapsed-label-set mode is explicitly out of scope, and the two intensity
rules' thresholds, conditions, severities and `evaluate` bodies are untouched
(only their declaration literals change). It adds **no corpus case**: the
intensity corpus keeps its four cases and gains fields. It does **not** edit
`vision.md` or `roadmap.md` (queue-020 scope fence): the ninth mode enters
through the specification, which is exactly what vision v3 §6 says should
happen. It does **not** retire or re-derive `FAILURE_MODE_NAMES` or
`MODE_RUNGS`, and does **not** add a ninth key to `MODE_ANCHOR_PATHS` — those
are item 147's, and mode 9's candidate features therefore carry
`role="hypothesised"`, never `"stage18-metric-anchor"`. It does **not** narrow
the catalogue's rule-granular mode attribution (item 148); mode 9 attaches to
every path the two intensity rules consume, and that is the expected,
temporary state.

## Acceptance Criteria

### The ninth mode

- [ ] **AC1: mode 9 is present with every schema field.** `SPECIFICATION[9]`
      exists; every field declared on `ModeSpec` is non-empty except where the
      schema permits emptiness, `observability == "needs-paired-scan"`,
      `provenance == "hypothesised"`, `severity` is a member of the accepted
      severity set (`Severity` labels minus `"pass"`), and the authored
      `status` is `"specified"` (a member of `AUTHORED_STATUSES`).

- [ ] **AC2: the definition states the modality and all three sub-shapes.**
      Mode 9's `definition` names CT as the modality and names each of the
      three tissue-implausibility shapes the two rules detect — implausibly
      low (soft tissue or air), implausibly high (metal or implant), and
      degenerate/uniform (near-zero spread).

- [ ] **AC3: the discriminator names a sibling mode.** Mode 9's
      `discriminator` contains at least one integer token that is the `id` of
      a different mode in `SPECIFICATION`, derived from the shipped ids rather
      than hardcoded.

- [ ] **AC4: mode 9's candidate features are hypothesised, and an anchor role
      is rejected.** Every `CandidateFeature` on mode 9 has
      `role == "hypothesised"`; constructing a `ModeSpec` with `id=9` and a
      `role="stage18-metric-anchor"` candidate raises `ValueError` whose
      message names mode 9 and `MODE_ANCHOR_PATHS`.

- [ ] **AC5: mode 9's edge set equals the live registry's.** The set of
      `intended_rules[].rule_id` on mode 9 equals
      `{rule_id for rule_id, decl in iter_rule_declarations() if decl is not
      None and 9 in decl.modes}`, computed live — and that set is
      `{"intensity", "intensity_reference_delta"}`.

- [ ] **AC6: each mode-9 edge's rung matches a fresh measurement.** For every
      edge on mode 9, `evidence_rung == "synthetic-demonstrable"` iff that
      edge's `rule_id` appears in the measured firing set of at least one of
      mode 9's corpus cases, and `"needs-real-data"` otherwise — the rungs
      are compared against a live measurement, never transcribed.

- [ ] **AC7: mode 9 derives `validated` from live state.**
      `derive_status(SPECIFICATION[9]) == "validated"`, computed live; and a
      probe built with `dataclasses.replace` that narrows one of mode 9's
      cases' `expected_firing` to a disagreeing set derives `"implemented"`,
      with the shipped `SPECIFICATION[9]` still deriving `"validated"`
      afterwards.

- [ ] **AC8: mode 9's rung is derived from its edges.**
      `derive_mode_rung(SPECIFICATION[9])` equals the strongest
      `EVIDENCE_RUNGS` member among mode 9's edges, and a probe whose
      strongest edge is weakened derives the weaker rung.

### The two rule declarations

- [ ] **AC9: both intensity rules declare mode 9.** `intensity` and
      `intensity_reference_delta` each carry a `RuleModeDeclaration` with
      `modes == (9,)`, `mode_less_reason == ""`, `pending_reason == ""` and a
      non-empty `evidence` tuple of non-empty strings.

- [ ] **AC10: neither declaration binds the reserved geometric-corpus tag.**
      `"corpus" not in decl.evidence` for both rules, and each declaration's
      `evidence` names `tests/corpus/intensity/manifest.json` — the corpus
      that actually demonstrates the mode.

- [ ] **AC11: the declaration↔specification check is clean in both
      directions on this tree.** `catalogue.rule_declaration_conflicts() == ()`;
      for every registered rule, every mode in its declaration is a key of
      `SPECIFICATION`; and for every mode in `SPECIFICATION`, every
      `intended_rules[].rule_id` names a registered rule whose declaration's
      `modes` contains that mode's `id`.

- [ ] **AC12: a mode absent from the specification is still reported.** A stub
      rule registered in an isolated registry declaring a mode id that is not
      a key of `SPECIFICATION` (and not a key of `MODE_ANCHOR_PATHS`) is
      reported by `rule_declaration_conflicts()`, with a message naming both
      the `rule_id` and the mode number, and matching the
      `^rule '([^']+)': declared §6 mode \d+ is outside` shape
      `traceability.build_matrix` parses.

- [ ] **AC13: the intensity rules' behaviour is unchanged.** Both modules'
      documented threshold constants hold their pre-item values
      (`DEFAULT_MIN_PLAUSIBLE_HU == 100.0`, `DEFAULT_MAX_PLAUSIBLE_HU ==
      2000.0`, `DEFAULT_MAX_DEGENERATE_STD == 1.0`, `DEFAULT_MAX_ROBUST_Z ==
      3.5`, `DEFAULT_MAX_DISTRIBUTION_DISTANCE == 3.0`), and replacing either
      rule's `mode_declaration` with an arbitrary valid declaration leaves
      `heuristics.run_rules`' output on a fixed record equal — the declaration
      is metadata the engine never reads.

### The public intensity harness

- [ ] **AC14: `synth/regression.py` exposes the intensity sibling.**
      `loaded_intensity_case` and `intensity_pipeline_findings` are defined in
      `segfacet.synth.regression`, listed in its `__all__`, and additively
      re-exported from `segfacet.synth` (importable as
      `from segfacet.synth import intensity_pipeline_findings`), with the
      signatures pinned in **A1**.

- [ ] **AC15: the harness composes the documented public path.**
      `intensity_pipeline_findings` reaches `segfacet.pipeline.
      run_qc_with_intensity` exactly once per call, with `reference=None` and
      `enable_pyradiomics=False`, and loads its images through
      `segfacet.io.load_case` — asserted by monkeypatching both and capturing
      the arguments, not by reading the source.

- [ ] **AC16: the harness measures every intensity case.** For each of the four
      cases in the committed intensity manifest, the sorted set of `rule_id`s
      among `intensity_pipeline_findings(case)`'s findings equals that case's
      manifest `expected_firing` list.

- [ ] **AC17: the harness is deterministic and non-mutating.** Two calls with
      the same manifest case return equal `(rule_id, severity.label,
      tuple(labels))` tuples in the same order, and the manifest case dict
      passed in compares equal to a deep copy taken before the call.

- [ ] **AC18: there is exactly one intensity composition in production.** No
      module under `src/segfacet/` other than `synth/regression.py` and
      `cli.py` both references `run_qc_with_intensity` and loads a case —
      asserted by an AST scan over `src/segfacet/**/*.py`, so the duplication
      `insights.md` recorded on 2026-09-03 cannot silently reappear. In
      particular `src/segfacet/traceability.py` references
      `run_qc_with_intensity` nowhere.

### `measured_firing` dispatch

- [ ] **AC19: `measured_firing` dispatches on the corpus.** A
      `CorpusCaseExpectation` with `corpus == "geometric"` resolves through the
      geometric manifest and `pipeline_findings` / `reconstructed_findings`;
      one with `corpus == "intensity"` resolves through the committed intensity
      manifest and `intensity_pipeline_findings`; any other `corpus` value
      raises `ValueError` naming the case id and the unrecognised corpus value.

- [ ] **AC20: mode 9's cases measure to their expected sets.** For every corpus
      case on mode 9, `set(measured_firing(case)) == set(case.expected_firing)`
      and `case_agrees(case) is True`; and `measured_firing(case)` equals the
      sorted rule-id set `intensity_pipeline_findings` returns for the same
      manifest case — one measurement path, not two.

- [ ] **AC21: the geometric dispatch is unchanged.** For every corpus case on
      each of modes 1–8, `case_agrees(case) is True` and `derive_status(mode)
      == "validated"` — the dispatch change moves no seed mode.

### The intensity manifest

- [ ] **AC22: every intensity case carries the new fields.** Each of the four
      cases in `tests/corpus/intensity/manifest.json` carries `failure_mode`
      (an `int`, not a `bool`), `failure_mode_name` (a non-empty `str`),
      `detection` (the literal `"intensity_pipeline"`) and `expected_firing`
      (a list of non-empty `str`, strictly ascending, no duplicates).

- [ ] **AC23: the failure-mode fields name the right mode.** `clean_hu` carries
      `failure_mode == 0` and `failure_mode_name ==
      synth.perturbation.FAILURE_MODE_NAMES[0]`; `implausible_metal`,
      `implausible_soft_tissue` and `degenerate_uniform` each carry
      `failure_mode == 9` and `failure_mode_name ==
      failure_modes.SPECIFICATION[9].name`, compared against the live values
      rather than transcribed literals.

- [ ] **AC24: every case's `expected_firing` equals a fresh measurement.** For
      each of the four cases, the manifest's `expected_firing` list equals the
      sorted rule-id set measured through `intensity_pipeline_findings`.

- [ ] **AC25: the generator writes the new fields byte-reproducibly.**
      `write_intensity_corpus(tmp)` into a fresh directory produces a
      `manifest.json` byte-identical to the committed
      `tests/corpus/intensity/manifest.json`; the committed file's bytes
      contain no `\r` and end in exactly one `\n`; and
      `.gitattributes` still pins `tests/corpus/intensity/manifest.json` as
      `text eol=lf`.

- [ ] **AC26: the manifest version is unchanged.**
      `INTENSITY_MANIFEST_VERSION == 1` and the committed manifest's
      `manifest_version` equals it — the change is additive, so no consumer of
      the version is invalidated.

### The first `proposed` entry

- [ ] **AC27: mode 10 is present as an unimplemented entry.**
      `SPECIFICATION[10]` exists with `status == "proposed"`,
      `intended_rules == ()`, `corpus_cases == ()`, and exactly one
      `CandidateFeature` whose `role == "hypothesised"` and whose `path` is the
      literal pinned in **A4**; its `definition` names the coincident-centroid
      mechanism (two labels sharing an exact centroid, Stage 3 degraded, every
      `stage3`-reading rule short-circuited, no finding raised) and its
      `discriminator` names a sibling mode id.

- [ ] **AC28: mode 10's status and rung are derived, not authored.**
      `derive_status(SPECIFICATION[10]) == "proposed"` and
      `derive_mode_rung(SPECIFICATION[10]) is None`, both computed live from
      the empty edge set and the empty corpus-case set.

- [ ] **AC29: an empty section renders legibly, not as a hole.**
      `render_markdown()`'s mode-10 block emits `- (none)` under both
      `Intended rules:` and `Corpus cases:`, and a probe mode with empty
      `candidate_features` emits `- (none)` under `Candidate features:` — no
      heading in the rendered output is followed immediately by a blank line
      and the next heading.

- [ ] **AC30: a `proposed` entry that acquires a declaring rule is reported.**
      With a stub rule registered in an isolated registry declaring mode 10,
      `specification_conflicts()` returns a non-empty tuple containing a
      message that names mode 10, its authored status `"proposed"` and the
      status `derive_status` now returns; on the shipped tree,
      `specification_conflicts() == ()`.

- [ ] **AC31: a `specified` entry that derives further is not reported.** The
      same check leaves modes 1–9 unreported even though every one of them
      derives `implemented` or `validated` while authored `"specified"` — the
      new conflict shape is specific to `proposed`, not a blanket
      authored-vs-derived equality.

### Artifacts and the record

- [ ] **AC32: the specification artifacts regenerate byte-identically.**
      `python -m segfacet.failure_modes --json <tmp> --md <tmp>` run twice
      produces byte-identical output, and each output is byte-identical to the
      committed `docs/aide/failure_modes.generated.json` /
      `docs/aide/failure_modes.generated.md`; both committed files are LF bytes
      ending in exactly one `\n`.

- [ ] **AC33: the downstream artifacts regenerate byte-identically.**
      `docs/aide/feature_catalogue.generated.{json,md}` and
      `docs/aide/traceability_matrix.generated.{json,md}` each regenerate
      byte-identically run-to-run and match their committed copies.

- [ ] **AC34: mode 9's catalogue attribution is exactly the declaring rules'
      reach.** For every entry in a freshly built catalogue, `9 in
      entry.failure_modes` iff at least one of `entry.consuming_rules` is a
      rule whose live declaration lists mode 9 — so no path outside the two
      intensity rules' reach acquired the mode.

- [ ] **AC35: the module records what had to change.**
      `segfacet.failure_modes.__doc__` carries a dated record of adding the
      ninth mode that names every production module this item changed; every
      repo-relative path named in that record resolves to a file that exists.

- [ ] **AC36: `aide check` is clean.** `python .aide/scripts/aide.py check`
      exits 0 and reports exactly the seven baseline warnings of **A10** — in
      particular no `.gitattributes` lint warning for any path this item
      writes.

## Assumptions

- **A1 (harness naming and signature):** the queue names no symbol, so this
  spec pins them. `segfacet.synth.regression` gains exactly two public names,
  mirroring `loaded_seg_image` / `pipeline_findings`:

      def loaded_intensity_case(
          case: dict, corpus_dir: Path = INTENSITY_CORPUS_DIR
      ) -> Tuple["nib.Nifti1Image", "nib.Nifti1Image"]:   # (seg_img, scan_img)

      def intensity_pipeline_findings(
          case: dict,
          config=None,
          *,
          reference=None,
          enable_pyradiomics: bool = False,
          corpus_dir: Path = INTENSITY_CORPUS_DIR,
      ) -> Tuple:

  No verdict-label sibling is added: nothing in this item needs one, and item
  149 may add it when the matrix does. `config=None` defaults to
  `bundled_default_config()`, exactly as `pipeline_findings` does.

- **A2 (`enable_pyradiomics=False` is pinned, not inherited):**
  `run_qc_with_intensity` defaults to `True`, which silently degrades to the
  builtin first-order backend when PyRadiomics is absent. The measured firing
  sets this item commits into two artifacts must not depend on an optional
  dependency — CI's `verify-environment-gated` job installs PyRadiomics, and an
  inherited `True` would let that job move a committed artifact. The harness
  therefore pins `False` and exposes it as a keyword so a caller can opt in.
  The Validation section replays the four cases under the `pyradiomics`
  profile to confirm the firing sets are in fact backend-independent.

- **A3 (`reference=None`):** the synthetic intensity corpus is not built against
  any reference distribution, so the harness passes `reference=None` — the same
  composition item 139's deferred spec described. A consequence: the
  `intensity_reference_delta` rule cannot fire on any of the four cases, which
  is why **A12** expects its mode-9 edge at `needs-real-data`.

- **A4 (the tenth mode's id and candidate path):** the `proposed` entry takes
  `id = 10`, the next free integer. Its single candidate feature path is
  `stage3_unavailable.reason` — record-relative, matching the eight seed modes'
  convention (`stage3.per_label_offsets[].offset_mm`,
  `relationships.is_continuous`), and resolving to
  `feature_report.build_features_block`'s `block["stage3_unavailable"]["reason"]`
  (item 129). The queue and roadmap write it informally as
  `features.stage3_unavailable`; that prefix is not a record path in this
  codebase, so the spec pins the resolvable form.

- **A5 (intensity manifest fields):** the four new per-case fields are
  `failure_mode` (int), `failure_mode_name` (str), `detection` (the constant
  `"intensity_pipeline"`) and `expected_firing` (list of rule ids, ascending).
  `expected_firing` is deliberately **not** named `expected_rule_ids`: the
  geometric manifest's field of that name is the *narrower designated* set,
  while this one is the *full* firing set, and reusing the name for a
  differently-scoped set is precisely the near-miss class `insights.md` recorded
  on 2026-09-02. `detection` is the dispatch key inside the intensity branch,
  mirroring the geometric manifest's discriminator; it has one legal value
  today and an unrecognised value must raise, never be skipped.

- **A6 (declaration evidence tag):** both declarations carry
  `evidence = ("intensity-corpus-manifest", "<one-sentence mechanism>")` and
  deliberately **not** the reserved `"corpus"` element. `"corpus"` is an
  exact-element membership test that binds the declaration→corpus direction
  against `catalogue._scan_synth_rule_mode_map()`, which AST-scans the
  `Expectation(...)` literals in `synth/*.py` — the **geometric** corpus only.
  Tagging `"corpus"` here would report a false conflict. Item 147 retires the
  tag entirely; until then AC10 makes the omission a deliberate, tested
  decision rather than an accident.

- **A7 (`catalogue.py`'s known-mode source moves here, not in item 147):**
  `rule_declaration_conflicts` currently validates declared modes against
  `feature_docs.MODE_ANCHOR_PATHS`'s key set (1–8), so declaring mode 9 would
  make `test_136::test_ac6_...` and `test_137::test_ac9_...` red the moment
  this item lands. The minimal honest fix is to source that check's known-mode
  set from `failure_modes.SPECIFICATION`'s keys (a deferred import inside the
  function, matching the existing `feature_docs` import) and to name the
  specification in the message. Behaviour for modes 1–8 is identical, because
  the specification carries all eight. Item 147 completes the collapse; this is
  the one line of it this item cannot defer. `MODE_ANCHOR_PATHS` itself is
  **not** changed, and its key set stays exactly 1–8.

- **A8 (`FAILURE_MODE_NAMES` and `MODE_ANCHOR_PATHS` are untouched):** adding a
  ninth key to `FAILURE_MODE_NAMES` would reach `eval/per_mode.py`,
  `eval/severity_ladder.py` and roughly a dozen test modules that pass it as
  the closed mode vocabulary of the *geometric* cohort. Deriving or retiring it
  is item 147's deliverable. The intensity manifest's `failure_mode_name` is
  therefore written from the generator's own recipe literal and pinned by AC23
  against the live `SPECIFICATION[9].name`, not imported from either map.

- **A9 (item 139 never landed, so there is nothing to re-point):** the
  2026-09-03 insight says item 139 "re-composed it privately inside
  `traceability.py`". Item 139 is ⏸️ Deferred and its code never merged —
  verified on this branch: `src/segfacet/traceability.py` contains zero
  occurrences of `intensity` and never references `run_qc_with_intensity`. So
  the "should `traceability.py`'s private composition call the public harness"
  question is answered by the tree: there is no such composition, this item
  writes none, and `traceability.py` is untouched (AC18 pins that it stays so).
  Item 149 re-points `build_matrix` and is the first consumer of the new
  harness.

- **A10 (engine 1.37.0):** `python .aide/scripts/aide.py check` on this branch
  reports **OK with 7 warnings**: 32 legacy specs without an `## Assumptions`
  block; human gates 1 and 2 awaiting a decision; and the four Stage-20
  criterion retraction notices (criteria 1, 3, 4, 5). AC36's baseline is that
  set. A new warning class is a finding, not a baseline update.

- **A11 (mode 9 severity):** `severity = "flagged-for-review"`, matching what
  both intensity rules actually emit by default
  (`_severity_from_param(default="flagged-for-review")`), and matching the eight
  seed modes. The builder confirms it against a measured finding's
  `severity.label` before authoring it.

- **A12 (expected edge rungs, to be confirmed by measurement):** `intensity` is
  expected at `synthetic-demonstrable` (the three implausible cases drive it
  end-to-end) and `intensity_reference_delta` at `needs-real-data` (it only
  fires when a reference distribution is attached, and **A3** attaches none —
  the same shape as item 145's analytic-only `reference_delta` edges). AC6
  derives both from a fresh measurement, so a measurement that disagrees is
  authored as measured, not forced to this assumption.

- **A13 (mode 9's name):** `"Implausible tissue under a label"` — vision §6's
  own wording for the ninth mode, title-cased to match the eight seed names
  (which are the §6 numbered-list titles verbatim). It is **not** parsed from
  §6's numbered list, because the ninth mode is deliberately not in it; that is
  the point of the item.

- **A14 (which cases are mode 9's):** mode 9's `corpus_cases` are the three
  implausible cases only. `clean_hu` is the negative control and carries
  `failure_mode = 0` in the manifest, exactly as the geometric manifest's
  `clean_control` does; it is measured and pinned at the manifest level
  (AC22/AC24) rather than attached to a mode whose failure it does not exhibit.

## Implementation Steps

1. **`src/segfacet/synth/regression.py` — the intensity harness.** Add
   `loaded_intensity_case` (resolve `case["scan_fixture"]` /
   `case["seg_fixture"]` under `INTENSITY_CORPUS_DIR`, call
   `segfacet.io.load_case`, rebuild both as `nib.Nifti1Image(data, affine,
   dtype=data.dtype)` — the explicit `dtype=` is mandatory for the int64 label
   array, item 040's Decisions log) and `intensity_pipeline_findings` (call
   `pipeline.run_qc_with_intensity(seg_img, scan_img, config, reference=…,
   enable_pyradiomics=…)` and return `case_result.findings`). Import
   `INTENSITY_CORPUS_DIR` from `segfacet.synth.intensity` at module level,
   mirroring the existing `from segfacet.synth.corpus import CORPUS_DIR`; if
   that import order causes a partially-initialised-package problem inside
   `synth/__init__.py`, defer it into the function bodies and record why.
   Extend `__all__` and the module docstring's "Public surface" paragraph.

2. **`src/segfacet/synth/__init__.py`** — add both names to the
   `from segfacet.synth.regression import (...)` block and to `__all__`,
   additively, in the existing alphabetical-within-block style.

3. **`src/segfacet/synth/intensity.py` — the manifest fields.** Add
   `failure_mode: int`, `failure_mode_name: str` and
   `expected_firing: Tuple[str, ...]` to `_RecipeEntry`; populate them in
   `CASE_RECIPE` (declared ground truth, exactly as `expected_label_hu_bands`
   is); carry them onto `IntensityCase`; emit them plus the constant
   `"detection": "intensity_pipeline"` in `write_intensity_corpus`'s
   `manifest_case` dict. The existing `json.dumps(..., indent=2,
   sort_keys=True) + "\n"` / `write_bytes` path is already correct — do not
   touch it, and do not bump `INTENSITY_MANIFEST_VERSION` (AC26, **A5**).
   Regenerate the committed corpus with
   `.venv/bin/python -m segfacet.synth.intensity`.

4. **Measure, then author.** With steps 1–3 in place, drive all four cases
   through `intensity_pipeline_findings` and record the measured rule-id sets;
   those measurements are what step 3's `CASE_RECIPE` literals and step 5's
   `expected_firing` tuples carry. Record the transcript in the Decisions log,
   the way item 145 recorded its measurement transcript. A case whose measured
   set is empty where a finding was expected is a **finding**: record it in
   `insights.md` and hand back — do not retune a threshold to make it fire.

5. **`src/segfacet/failure_modes.py` — modes 9 and 10.** Add `_MODE_9` and
   `_MODE_10` and extend the `_build_specification((...))` tuple. Mode 9 per
   AC1–AC8 and **A11**/**A12**/**A13**/**A14**, with `corpus="intensity"` on
   each `CorpusCaseExpectation` and a `reason` naming the harness, the corpus
   and the measurement date (item 145's reason style). Mode 10 per AC27 and
   **A4**.

6. **`src/segfacet/failure_modes.py` — `measured_firing` dispatch.** Branch on
   `case.corpus` first: `"geometric"` keeps today's body verbatim;
   `"intensity"` loads
   `segfacet.synth.intensity.load_intensity_manifest()`, finds the case by
   `case_id` (raising with the same message shape when absent), reads its
   `detection`, and calls `intensity_pipeline_findings` for
   `"intensity_pipeline"` — raising `ValueError` for any other `detection`.
   Any other `corpus` value raises `ValueError` naming both. Update the
   docstring, which today says the `corpus` field "is informational, not a
   dispatch key".

7. **`src/segfacet/failure_modes.py` — `specification_conflicts`.** Keep the
   existing out-of-vocabulary check and add the `proposed`-drift check: for a
   mode whose authored `status == "proposed"`, report when
   `derive_status(mode) != "proposed"`, naming the mode id, `"proposed"`, and
   the derived value. Do **not** generalise to all authored statuses — AC31.

8. **`src/segfacet/failure_modes.py` — `render_markdown`.** Emit `- (none)`
   under `Candidate features:`, `Intended rules:` and `Corpus cases:` when the
   corresponding list is empty.

9. **`src/segfacet/failure_modes.py` — the docstring record.** Add an "Adding
   the ninth mode (item 146, 2026-09-0N)" section listing every production
   module this item changed and one line on what each change was, plus the
   sentence this is evidence for: a mode entered through the schema, its status
   derived, without the eight seed entries or the rule engine being rebuilt.
   Update the "The ninth mode and the first `proposed` entry are item 146's"
   sentence, which is now done.

10. **`src/segfacet/heuristics/intensity.py` and
    `intensity_reference_delta.py`.** Replace each `mode_declaration =
    RuleModeDeclaration(mode_less_reason=...)` literal with
    `RuleModeDeclaration(modes=(9,), evidence=(...))` per **A6**. Nothing else
    in either file changes — no threshold, no tag string, no condition, no
    `evaluate` line. Move the substance of the retired `mode_less_reason`
    (which tissue signal each rule judges, and which corpus demonstrates it)
    into the evidence sentence and, where it belongs to the mode rather than
    the rule, into mode 9's `definition` / `discriminator`.

11. **`src/segfacet/catalogue.py` — the known-mode source.** In
    `rule_declaration_conflicts`, replace
    `known_modes = set(feature_docs.MODE_ANCHOR_PATHS.keys())` with the
    specification's key set via a deferred `from segfacet import failure_modes`,
    and update the message to name the specification. Keep the message prefix
    `rule '<id>': declared §6 mode <n> is outside …` byte-compatible with
    `traceability.build_matrix`'s regex (which matches only up to `is
    outside`). Update the function docstring's fourth bullet. Nothing else in
    `catalogue.py` changes.

12. **Regenerate the four artifact pairs** —
    `python -m segfacet.failure_modes`, `python -m segfacet.catalogue`,
    `python -m segfacet.traceability` (each through `.venv/bin/python`) — and
    confirm the catalogue's diff is exactly mode 9 appearing on
    intensity-consumed paths plus the `rule_mode_less` tag disappearing, and
    the matrix's diff is exactly the two rules' `declaration_state` /`modes`
    moving from `mode_less` to `declared`.

13. **Reconcile the existing tests** named in the Testing Strategy. Every
    reconciliation is a *rescoping* to the state that now exists — never a
    weakened assertion for any of the eight seed modes.

## Authorised paths

**May change:**

- `src/segfacet/failure_modes.py` — modes 9 and 10, `measured_firing`'s corpus
  dispatch, `specification_conflicts`' `proposed`-drift check,
  `render_markdown`'s empty-section rendering, and the docstring record.
- `src/segfacet/heuristics/intensity.py` — the `mode_declaration` literal
  only (step 10).
- `src/segfacet/heuristics/intensity_reference_delta.py` — the
  `mode_declaration` literal only (step 10).
- `src/segfacet/synth/regression.py` — the two new public functions, their
  imports, `__all__` and the docstring's public-surface paragraph.
- `src/segfacet/synth/__init__.py` — additive re-export of those two names.
- `src/segfacet/synth/intensity.py` — `_RecipeEntry` / `CASE_RECIPE` /
  `IntensityCase` / `write_intensity_corpus`'s four new manifest fields.
- `src/segfacet/catalogue.py` — `rule_declaration_conflicts`' known-mode source
  and its message/docstring only (**A7**); no other function.
- `tests/corpus/intensity/manifest.json` — regenerated by
  `segfacet.synth.intensity`, never hand-edited.
- `docs/aide/failure_modes.generated.json` — regenerated conformance artifact.
- `docs/aide/failure_modes.generated.md` — regenerated review surface.
- `docs/aide/feature_catalogue.generated.json` — regenerated; the diff is
  mode 9's attribution.
- `docs/aide/feature_catalogue.generated.md` — the same.
- `docs/aide/traceability_matrix.generated.json` — regenerated; the diff is the
  two rules' declaration state.
- `docs/aide/traceability_matrix.generated.md` — the same.
- `tests/test_146_ninth_mode_and_first_proposed.py` — this item's tests.
- `tests/test_144_failure_mode_specification.py` — reconciliation only:
  `test_ac16_specification_carries_all_eight_modes` and
  `test_ac16_names_match_vision_section_six_parsed_titles` are rescoped to the
  eight seed modes. No other assertion in that module is touched.
- `tests/test_145_eight_hypothesised_modes.py` — reconciliation only:
  `test_ac1_all_eight_modes_present`,
  `test_ac3_names_match_vision_section_six_parsed_titles`,
  `test_ac8_every_synthetic_demonstrable_edge_is_demonstrated`,
  `test_ac13_every_expected_firing_equals_fresh_measurement_and_all_validated`,
  `test_ac20_detector_names_the_detector_that_actually_fired` and
  `test_ac21_severity_grounded_in_a_measured_finding` are rescoped to
  `_EXPECTED_MODE_IDS`. No assertion about any of the eight is weakened.
- `tests/test_137_mode_less_rule_disposition.py` — reconciliation only: the
  `_MODE_LESS` roll call and the six tests that read it or pin the pre-item
  manifest shape (listed in the Testing Strategy).
- `tests/test_103_feature_catalogue.py` — reconciliation only:
  `test_ac15_..._mode_less_...` (the "entries consumed only by the mode-less
  pair" test, line ~615), which has no mode-less pair left to select.
- `tests/test_138_traceability_matrix.py` — reconciliation only:
  `test_adv_rule_declaring_only_an_uncatalogued_mode_makes_rule_to_mode_a_hole`,
  whose stub declares `modes=(9,)` as its uncatalogued example and must move to
  a mode absent from **both** `SPECIFICATION` and `MODE_ANCHOR_PATHS`.

**Asserts against:**

- `docs/aide/vision.md` — §6's principles are the source of the lifecycle,
  observability and provenance vocabularies this item exercises; read-only, and
  changed only through its own loop entry point (queue-020 scope fence). The
  rescoped conformance check reads §6's numbered list for the **eight seed
  modes only**.
- `src/segfacet/feature_docs.py` — AC4 and AC12 read `MODE_ANCHOR_PATHS` live;
  its key set stays exactly 1–8 and this item writes nothing here.
- `src/segfacet/heuristics/rule.py` — AC5/AC9/AC11 read `RuleModeDeclaration`
  and `iter_rule_declarations`; the schema itself is item 147's.
- `src/segfacet/heuristics/runner.py` — AC13 drives `run_rules`.
- `src/segfacet/verdict.py` — AC1's accepted severity set derives from
  `Severity`.
- `src/segfacet/pipeline.py` — AC15 pins the `run_qc_with_intensity` call
  shape; AC16/AC24 measure through it.
- `src/segfacet/io.py` — AC15 pins the `load_case` load path.
- `src/segfacet/synth/perturbation.py` — AC23 reads `FAILURE_MODE_NAMES[0]`;
  the map is not changed here (**A8**).
- `src/segfacet/synth/corpus.py` — AC19/AC21 resolve geometric cases through
  `load_manifest`.
- `src/segfacet/traceability.py` — AC18 pins that this module contains no
  intensity composition, and AC12 pins that the conflict message stays
  compatible with `build_matrix`'s regex. Nothing here is written; item 149
  re-points `build_matrix`, and that item's spec lists this file under
  **May change**.
- `src/segfacet/feature_report.py` — **A4**'s `stage3_unavailable` record key.
- `tests/corpus/intensity/fixtures/*.nii.gz` — AC16/AC24 recompute firing sets
  live from these committed fixtures; unchanged (only intensities were ever
  painted here, and no fixture is regenerated by this item).
- `tests/corpus/manifest.json` — AC21 re-measures the eight seed modes' cases
  at their post-item-143 values; no case is added or changed.
- `tests/corpus/fixtures/*.nii.gz` — AC21's geometric measurements read these.
- `.gitattributes` — AC25 reads the existing `text eol=lf` pin for the
  intensity manifest; already present, so this item adds no line.
- `tests/committed_artifact_guard.py` — the intensity manifest and both
  generated-artifact pairs are already allowlisted there; read as the guard the
  byte-exactness claims run under. The sixth `no-float-leaf` ground is item
  149's.
- `.aide/VERSION` — **A10**'s engine marker.

## Testing Strategy

New module: **`tests/test_146_ninth_mode_and_first_proposed.py`**, one focused
test per AC, in AC order, with the module docstring listing the AC → test map
(house style, items 144/145).

**Fixtures and cost.** Every measurement goes through one module-scoped cache
keyed by `case_id`, as item 145 does: a `measured` fixture wrapping
`failure_modes.measured_firing` and an `intensity_corpus` fixture wrapping
`intensity_pipeline_findings`. `run_qc_with_intensity` over four cases is the
expensive part of this module; nothing may call it per-parametrisation without
the cache. A cache **inside** production code is forbidden — it would defeat
the adversarial tests that prove the derivations are live.

**Adversarial and edge cases, beyond the one-per-AC set:**

- `CorpusCaseExpectation(corpus="intensity", case_id="__nonexistent__")` →
  `ValueError` naming the case id and the intensity manifest, not a `KeyError`
  or a silent empty set.
- `CorpusCaseExpectation(corpus="", …)` and `corpus="Intensity"` (wrong case) →
  `ValueError`; the dispatch vocabulary is closed and exact.
- A manifest case whose `detection` is an unrecognised string → `ValueError`
  naming the case, mirroring `reconstructed_findings`' contract.
- `ModeSpec(id=9, …)` with `corpus_cases` holding a bare `str`
  `expected_firing` → rejected at construction (item 144 AC7's character-wise
  comparison trap), and `case_agrees` rejects it too.
- Constructing mode 10 with a non-empty `intended_rules` but `status="proposed"`
  is *legal* at construction — the contradiction is a
  `specification_conflicts` finding, not a `ValueError`; assert both halves so
  the boundary is explicit.
- `render_markdown()` twice → equal strings; `specification_to_dict()` twice →
  equal dicts, and mutating the first leaves the second unchanged (mode 10's
  empty lists must not be shared objects).
- Registering the AC12/AC30 stubs uses the module's `isolated_registry`
  fixture; assert the shipped registry is restored afterwards.
- `intensity_pipeline_findings` with an explicit `config=` that disables the
  `intensity` rule → the returned set loses `intensity` and nothing else,
  proving the harness forwards the config rather than ignoring it.
- Determinism of the whole rendering under a different `PYTHONHASHSEED` is
  already covered by the byte-identity tests; do not re-add.

**Existing tests to reconcile** (each is a claim about a state that this item
deliberately changes; every one is a *rescoping*, never a weakening, and each
gets a comment naming item 146 and the reason, as items 137/145 did):

- `tests/test_144_failure_mode_specification.py`
  - `test_ac16_specification_carries_all_eight_modes` — `ids == (1..8)` becomes
    "the eight seed ids are present, in ascending order, as the first eight".
  - `test_ac16_names_match_vision_section_six_parsed_titles` — iterate the eight
    seed ids, not `iter_modes()`. (`test_ac16_each_id_is_a_key_of_mode_anchor_paths`
    is already parametrised over `[1..8]` and needs no change.)
- `tests/test_145_eight_hypothesised_modes.py`
  - `test_ac1_all_eight_modes_present` — same rescoping as above.
  - `test_ac3_names_match_vision_section_six_parsed_titles` — same; this is
    item 147's one kept conformance check in the vision→specification
    direction, and its rescoped form is "**the eight seed modes'** names equal
    §6's list".
  - `test_ac8_every_synthetic_demonstrable_edge_is_demonstrated`,
    `test_ac20_detector_names_the_detector_that_actually_fired`,
    `test_ac21_severity_grounded_in_a_measured_finding` — these resolve each
    case through `_manifest_case` / the `corpus` fixture, which read the
    **geometric** manifest and would raise on mode 9's intensity cases; skip
    modes outside `_EXPECTED_MODE_IDS`.
  - `test_ac13_every_expected_firing_equals_fresh_measurement_and_all_validated`
    — asserts `mode.corpus_cases` non-empty and `derive_status == "validated"`
    for every shipped mode; mode 10 has neither. Restrict to
    `_EXPECTED_MODE_IDS`. Mode 9's equivalent is AC20 in this item's module.
  - `test_ac19_every_discriminator_names_a_sibling_mode` and
    `test_adv_all_expected_firing_tuples_are_ascending` iterate every shipped
    mode and **must keep doing so** — AC3 and AC27 exist so modes 9 and 10
    satisfy them.
- `tests/test_137_mode_less_rule_disposition.py`
  - `_MODE_LESS` — no rule ships mode-less after this item; the roll call
    becomes empty and the tests that select on it must be rescoped, not
    deleted.
  - `test_ac5_mode_less_rule_declares_no_modes_not_pending` and
    `test_ac6_mode_less_reason_is_substantive` — parametrised over `_MODE_LESS`;
    restate as "the two intensity rules are dispositioned, not pending, and now
    declare mode 9".
  - `test_ac7_intensity_reason_cites_corpus_manifest_path` — reads
    `mode_less_reason`, now `""`; the claim moves to the declaration's
    `evidence` (this item's AC10).
  - `test_ac8_intensity_manifest_has_no_failure_mode_field_and_named_cases` —
    asserts `"failure_mode" not in case`, directly inverted by AC22; restate as
    "every case carries `failure_mode`, and the four case ids are unchanged".
  - `test_ac10_rule_mode_less_tag_present_iff_mode_less_consuming_rule` — the
    `iff` half is derived and still holds, but `assert checked_true` requires at
    least one `rule_mode_less`-tagged entry and there is none; restate the
    liveness half.
  - `test_adv_shared_reference_delta_and_mode_less_entry_carries_both_tags_ordered`
    — selects entries shared between an analytic and a mode-less rule (none
    left) and pins `failure_modes == (1, 2)` on them (now `(1, 2, 9)`); restate
    against the post-item state, with the note that item 148 narrows the
    bookkeeping paths.
  - `test_adv_per_label_container_keeps_corpus_modes_and_gains_mode_less_last`
    — same cause.
  - `test_ac14_intensity_only_non_anchor_entries_are_honestly_mode_less` — the
    honesty claim survives in a new form: an intensity-only, non-anchor entry
    now carries `failure_modes == (9,)` and a `rule_declaration` tag, which is
    *more* honest, not less.
  - `test_adv_measured_artifact_movement_counts_from_spec` — its
    `mode_evidence`-combination counts move; re-measure and record the new
    counts with what they were measured on.
  - `test_ac17_mode_anchor_paths_key_set_still_one_through_eight` and
    `test_ac17_vision_section_six_still_has_exactly_eight_modes` **must keep
    passing unchanged** — they are the guards that this item added its mode to
    the specification and not to either of those two sources.
- `tests/test_103_feature_catalogue.py`
  - the mode-less-only-entry test (line ~615) — same cause as test_137's AC14;
    restate for the state that now exists, keeping the honesty claim.
- `tests/test_138_traceability_matrix.py`
  - `test_adv_rule_declaring_only_an_uncatalogued_mode_makes_rule_to_mode_a_hole`
    — its stub declares `modes=(9,)` and asserts `9 not in MODE_ANCHOR_PATHS`.
    Mode 9 is now specified, so `rule_declaration_conflicts` no longer reports
    it and `rule_to_mode` stays complete. Move the stub to a mode absent from
    both `SPECIFICATION` and `MODE_ANCHOR_PATHS` (e.g. `99`) and assert that
    absence live rather than by literal.
- `tests/test_136_rule_mode_declarations.py`, `tests/test_058_intensity_fixtures.py`
  and `tests/test_106_stage19_validation.py` were checked and need **no**
  change: every relevant assertion there is derived from live declaration state
  or from `MODE_ANCHOR_PATHS`, and `INTENSITY_MANIFEST_VERSION` is not bumped.
  If any of the three does go red, that is a finding to report, not a file to
  quietly edit — none is authorised here.

## Validation

Beyond the suite, replay the two claims the tests can only make on the loop
machine's environment:

1. **Backend independence of the committed firing sets** (**A2**). With the
   `pyradiomics` profile available
   (`python .aide/scripts/aide.py env --profile pyradiomics`), drive the four
   intensity cases through `intensity_pipeline_findings` with
   `enable_pyradiomics=True` and confirm each case's rule-id set equals the
   committed `expected_firing`. If the profile is **absent**, record
   **❓ Unverified** with the reason — never a silent pass — and note that
   CI's `verify-environment-gated` job is where it is actually exercised.
2. **The rendering a person will read** (item 150's review surface).
   `.venv/bin/python -m segfacet.failure_modes --md <tmp>/preview.md`, then read
   the mode-9 and mode-10 blocks: mode 9 must show `needs-paired-scan`, both
   edges with their rungs, and its three corpus cases each with an expected
   firing set and `agrees: True`; mode 10 must show `proposed`, `none` for the
   derived rung, and `- (none)` under both empty sections. A block that reads
   as a hole is an AC29 failure even if the assertion passed.

## Dependencies

- **Item 143** ✅ — the S-axis correction. Every firing set measured here is
  measured on the corrected corpus; the intensity corpus was regenerated under
  it.
- **Item 144** ✅ — `ModeSpec`, the closed vocabularies, `derive_status`,
  `measured_firing`, `specification_conflicts`, `render_markdown` and the two
  generated artifacts. This item extends four of those six functions.
- **Item 145** ✅ — the eight seed entries, the per-edge rung convention, the
  `reason` style for a `CorpusCaseExpectation`, and the measured-then-authored
  discipline this item repeats for the intensity corpus.

**Downstream:** item 147 collapses the five partial sources onto the
specification and completes the `catalogue.py` change **A7** begins, retires the
`"corpus"` evidence tag this item deliberately does not bind (**A6**), and keeps
the rescoped eight-seed-name conformance check as its one vision→specification
direction. Item 148 narrows the rule-granular attribution mode 9 inherits.
Item 149 re-points `build_matrix` at the specification and is the first consumer
of `intensity_pipeline_findings` outside `measured_firing`. Item 150's sign-off
reads modes 9 and 10 in the rendering. Item 151 replays the stage.

## Decisions & Trade-offs

### The measurement transcript (2026-09-04)

Every `expected_firing` literal committed by this item — into
`tests/corpus/intensity/manifest.json`'s `CASE_RECIPE` and into mode 9's
`CorpusCaseExpectation`s — was measured first, through the new public harness
`segfacet.synth.regression.intensity_pipeline_findings` (default
`reference=None`, `enable_pyradiomics=False`), on this branch, and then
transcribed. Measured firing sets:

| case | `failure_mode` | measured rule-id set | findings raised |
|---|---|---|---|
| `clean_hu` | 0 | `[]` | none |
| `implausible_metal` | 9 | `["intensity"]` | 1 — *(too high)*: label 22 median 2999.00 HU above the 2000.00 HU ceiling |
| `implausible_soft_tissue` | 9 | `["intensity"]` | 1 — *(too low)*: label 22 median 40.00 HU below the 100.00 HU floor |
| `degenerate_uniform` | 9 | `["intensity"]` | 2 — *(too low)*: median 0.00 HU, **and** *(degenerate/uniform)*: std 0.00 HU at/below the 1.00 HU threshold |

Three consequences, all authored as measured rather than as assumed:

- **A11 confirmed.** Every measured finding carries `severity.label ==
  "flagged-for-review"`, so mode 9's `severity` is authored to match what the
  rules actually emit.
- **A12 confirmed.** `intensity` fires on all three implausible cases →
  `evidence_rung="synthetic-demonstrable"`. `intensity_reference_delta` fires
  on none — the synthetic intensity corpus is built against no reference
  distribution and the harness attaches none (A3) — so its mode-9 edge is
  authored `needs-real-data`, the same analytic-only shape item 145 recorded
  for `reference_delta`.
- **`degenerate_uniform` raises two findings from one rule.** Its constant 0 HU
  fill trips both the degenerate/uniform detector and the too-low detector.
  The firing *set* is still `{intensity}`, which is what both artifacts carry;
  the two-finding detail is recorded in that case's `reason` so a later reader
  does not mistake the single-element set for a single finding.

`clean_hu` measures to the empty set and is **not** attached to mode 9 (A14):
it is the negative control, carrying `failure_mode = 0` /
`failure_mode_name = "clean control (no failure)"` at the manifest level,
exactly as the geometric manifest's `clean_control` does.

### What had to change to add a mode (AC35's record)

The same list is written into `segfacet.failure_modes.__doc__` as an
"Adding the ninth mode (item 146, 2026-09-04)" section, where a reader of the
module finds it without this spec. Six production modules, and nothing else —
in particular no rule's `evaluate` body, no threshold, no `ModeSpec` schema
field, no seed mode, and neither root document:

- `src/segfacet/failure_modes.py` — `_MODE_9` / `_MODE_10` authored and
  appended to `_build_specification`; `measured_firing` gained a first-level
  dispatch on `CorpusCaseExpectation.corpus`; `specification_conflicts` gained
  the `proposed`-drift check; `render_markdown` gained `- (none)`;
  `derive_status` gained the declaring-rule precondition (below).
- `src/segfacet/heuristics/intensity.py`,
  `src/segfacet/heuristics/intensity_reference_delta.py` — the
  `mode_declaration` literal only, mode-less → `modes=(9,)` with an
  `evidence` tuple naming `tests/corpus/intensity/manifest.json`. The two
  now-false "mode-less (item 137)" sentences in each module's docstring and
  the comment directly above each declaration were corrected in the same
  edit: leaving prose that contradicts the literal beside it would have been
  a worse outcome than the narrowest possible diff, and AC13 pins that
  neither rule's *behaviour* moved (both threshold constants sets hold, and
  `run_rules`' output on a fixed record is invariant to the declaration).
- `src/segfacet/synth/regression.py` — `loaded_intensity_case` and
  `intensity_pipeline_findings`. The `from segfacet.synth.intensity import
  INTENSITY_CORPUS_DIR` module-level import raised no partially-initialised
  package problem (Implementation Step 1's contingency), so no deferral was
  needed.
- `src/segfacet/synth/__init__.py` — both names re-exported, additively.
- `src/segfacet/synth/intensity.py` — the four new per-case manifest fields,
  written by the generator at an unchanged `INTENSITY_MANIFEST_VERSION`.
- `src/segfacet/catalogue.py` — `rule_declaration_conflicts`' known-mode set
  moved from `feature_docs.MODE_ANCHOR_PATHS`' keys to
  `failure_modes.SPECIFICATION`' keys (A7), via a deferred import matching
  the existing `feature_docs` one. The message prefix `rule '<id>': declared
  §6 mode <n> is outside …` is byte-unchanged up to `is outside`, which is
  all `traceability.build_matrix`'s regex matches.

The regenerated artifact diffs are exactly what the spec predicted: the
catalogue gains mode 9 on the intensity-consumed paths and loses the
`rule_mode_less` tag; the matrix moves both intensity rules from `mode_less`
to `declared` with `modes = 9`.

### `derive_status`: `validated` now requires a declaring rule

The item-145 review finding (`docs/aide/insights.md`, item 145, 2026-09-03)
is fixed here rather than deferred, because this item is the first to add a
mode whose rules arrive in the same change: `derive_status` tested the
corpus-agreement clause first, so a mode with agreeing corpus cases and **no
rule declaring it anywhere** derived `"validated"` without ever passing
through `"implemented"`. vision §6's ladder is cumulative — validated implies
implemented — so `_registry_declares(mode.id)` is now a precondition on
`"validated"`, not merely the fallback below it. No shipped mode moves: modes
1–9 all derive `validated` as before (verified live on this branch), and mode
10 derives `proposed` from its empty edge and case sets. Recorded in the
module docstring's `derive_status` entry.

### One authorised test reconciliation beyond the spec's list

`tests/test_145_eight_hypothesised_modes.py::test_ac23_fresh_matches_committed_structurally_and_carries_all_eight_ids`
asserted `committed_ids == set(_EXPECTED_MODE_IDS)` against the committed
`failure_modes.generated.json`. Item 146 regenerates that artifact to carry
modes 9 and 10, so the equality would go red on a state this item
deliberately created. It is narrowed to `set(_EXPECTED_MODE_IDS) <=
committed_ids` — a value reconciliation that keeps the module's eight-id
claim intact and stops it pinning the artifact's total mode count, which
`test_146`'s AC32 asserts live instead. The test-writer captured this as a
defect (`insights.md`, item 146, 2026-09-04) because it was outside their
authorised scope; this is where it is acted on. No other test assertion was
touched.

### Validation

1. **Backend independence of the committed firing sets (A2)** — **❓
   Unverified.** The measurement above ran with `enable_pyradiomics=False`,
   which is the value the harness pins precisely so a committed artifact
   cannot move with an optional dependency. The `pyradiomics` profile's
   availability on this machine was not established as part of this item, so
   the `enable_pyradiomics=True` replay is recorded as unverified rather than
   as a silent pass. CI's `verify-environment-gated` job is where the claim is
   actually exercised.
2. **The rendering a person will read** — mode 9's block in
   `docs/aide/failure_modes.generated.md` shows `needs-paired-scan`, both
   edges with their rungs (`intensity` at `synthetic-demonstrable`,
   `intensity_reference_delta` at `needs-real-data`), and its three corpus
   cases each with an expected firing set and `agrees with live measurement:
   True`. Mode 10's block shows `Status, authored: proposed`, `Status, derived
   (live): proposed`, `Derived rung (strongest edge, live): none`, and
   `- (none)` under both `Intended rules:` and `Corpus cases:` — it reads as a
   deliberate absence, not a hole.
