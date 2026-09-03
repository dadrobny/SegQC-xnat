# Item 143 — Correct the synthetic corpus's S-axis stacking before anything is measured

> **Created:** 2026-09-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source (deliverable **D0**)
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 143
> **Objectives:** G2 (detect catalogued failure modes — the corpus every mode's
> expected firing set is measured on), G3 (distinguish failure from variation —
> the synthetic reference artifact built from the same generator), G7 (evaluable
> & regression-testable)
> **Suggested branch:** `aide/143-correct-the-synthetic-corpus-s`

---

## Description

`src/segfacet/synth/clean_gt.py::build_clean_spine` places ascending labels at
**ascending** array-axis-2 slots (`start2 = margin_vox_si + i * (body + gap)`
for the `i`-th label, `clean_gt.py:284`). Item 116 made axis 2 the
superior-inferior axis and made the affine truthful about it, so the emitted
volume is RAS-native — but the *label order along* that axis was never
questioned. `pipeline.extract_feature_record` orders centroids by ascending
label, which item 093 pins as head-to-tail (`20 = L1 … 24 = L5`), so today
`clean_control` places `L1` at `S = 27 mm` and `L5` at `S = 187 mm`: the lumbar
spine upside down, with every in-repo driver advancing **superiorly** while real
VerSe input read through `segfacet.io` advances **caudally** (measured
2026-08-31, `insights/archive-2026-Q3.md`, item 131; the same entry records the
real-cohort net advance of −26 to −364 mm over the first eight VerSe19
subjects).

That single inversion is why item 131's traversal-direction defect stayed
invisible for nine items — item 122's direction normalisation was a no-op across
the entire committed surface — and it flips the sign of any future feature
measured against `+S`. Item 131 fixed the one array and explicitly did **not**
fix the corpus ("does not … correct the synthetic corpus's inverted `S`
stacking", item 131 spec, *What this item is NOT*).

This item corrects the stacking so ascending labels advance caudally like real
input, then regenerates every committed value the change moves and records, per
committed artifact, **whether it moved and by how much**. It lands first and
alone in queue-020 because every expected firing set items 145 and 146 author,
and the specificity baseline Stage 20's ratchet later pins, must be measured on
the corrected corpus.

**The correction is a label↔slot reassignment, not a reshaping.** The body
layout is symmetric about the S midpoint (equal margins at both ends; the
lateral hump `amplitude * sin(pi * i / (n - 1))` is symmetric in `i`), so
placing the `i`-th label at slot `n - 1 - i` produces the *same* solid blocks in
the same places with the label values reversed. Per-label voxel counts, extents,
volumes, the emitted shape and the affine are all unchanged; what changes is
which label sits at which S, and therefore every S-signed measurement derived
from it.

**In scope.** The stacking direction in `clean_gt.py` and its docstring
contract; regeneration of the geometric corpus, the intensity corpus, the
synthetic-cohort reference artifact and every committed generated artifact
downstream of the corpus; the per-artifact moved/unmoved record; reconciliation
of every test whose *expected value* moved.

**Not in scope — and the hand-back rule.** This is a **corpus-value change, not
a rule change**. No threshold or rule under `src/segfacet/heuristics/` may
change, and no case's designated `(rule_id, labels)` may move. If a rule's
firing set moves under the corrected corpus, that is a **finding**: record one
line in [`insights.md`](../insights.md) and hand back — never retune a threshold
or edit a rule to keep a green suite green. Also not in scope: the operators
under `src/segfacet/synth/` (item 116 made every one of them resolve its axis
from the affine, so none should need a change); `reference_verse_v1.json`'s
contents (built from the real VerSe19 cohort, which no synthetic input feeds);
item 131's canonical convention phrase `normalised so the sequence advances
superiorly`, which describes the *output* of the normalisation and stays correct
under a caudal-advancing input.

## Acceptance Criteria

- [ ] **AC1: ascending labels advance caudally in the built array.** For
  `build_clean_spine()` (defaults), the per-label centroid coordinate along the
  affine-resolved S/I axis (`segfacet.synth.axes.si_axis`) is **strictly
  decreasing** over `spine.labels` in ascending order — asserted on
  `np.asanyarray(spine.seg_img.dataobj)` directly, not through any feature
  extractor, rule, report or committed fixture.

- [ ] **AC2: the caudal order holds for every span and spacing.** The same
  strict decrease holds for a cervical span (`levels=("C3","C4","C5")`), a
  two-level span, a five-level span at anisotropic spacing
  `(0.8, 1.2, 3.0)`, and with `curve_amplitude_mm=0.0`.

- [ ] **AC3: the correction reassigns labels and does not reshape the spine.**
  For the default build, mirroring the label array along the S/I axis and then
  reversing the label↔level assignment reproduces the array exactly
  (`data[:, :, ::-1]` with labels remapped `labels[i] -> labels[n-1-i]` equals
  `data`), and `spine.shape`, `spine.spacing`, `spine.seg_img.affine` and every
  entry of `spine.voxel_counts` are what the pre-item generator produced for the
  same arguments. The physical spine is the same spine; only the label order
  along S is corrected.

- [ ] **AC4: item 116's contract survives intact.** `build_clean_spine` still
  stacks along array axis 2, the affine still resolves S/I onto axis 2, and
  loading a generated fixture through `segfacet.io` is still an array-identity
  operation — `tests/test_116_ras_native_corpus.py` passes with no assertion
  weakened or removed.

- [ ] **AC5: the docstring states the corrected contract.** `clean_gt.py`'s
  module docstring and `build_clean_spine.__doc__` each state that ascending
  labels advance **caudally** (descending S), matching real VerSe input read
  through `segfacet.io`, and neither states or implies that ascending labels
  occupy ascending axis-2 positions. A canonical key phrase (chosen by the
  builder, e.g. `ascending labels advance caudally`) appears in both and is
  asserted by name.

- [ ] **AC6: every corpus case advances caudally.** For every case in
  `tests/corpus/manifest.json`, the ascending-label-ordered centroid sequence's
  net `+S` advance (`centroids[-1].centroid_mm[2] - centroids[0].centroid_mm[2]`)
  is **negative**, and
  `tests/test_131_tangent_direction_normalisation.py::_PRE_ITEM_NET_ADVANCE_S_MM`
  is updated to the regenerated per-case measurements (expected, from AC3's
  symmetry, to be the negation of each pre-item entry: `−160.0` mm for eight
  cases and `−142.0` mm for `mode8_force_overlap`; the committed table carries
  what was measured, not what this spec predicted).

- [ ] **AC7: `tangent_angles_deg` does not move on the eight non-doubling-back
  cases.** `test_131`'s `_PRE_ITEM_TANGENT_ANGLES_DEG` table still holds within
  `abs=1e-3` for every case except `mode4_relabel_swap`, with the table's values
  unchanged — item 131's normalisation is exactly what makes a caudal-advancing
  corpus read the same, and this AC is the evidence that it works.

- [ ] **AC8: `mode4_relabel_swap`'s tangent angles move only by item 131's
  measured fit asymmetry.** That case's `tangent_angles_deg` matches the same
  unchanged table entry within `abs=1e-2`, with the loosened tolerance named in
  the failure message and attributed to spline-fit asymmetry on a curve that
  reverses in S (item 131 AC3 measured the residual at `6.563e-03°`), not to a
  convention difference.

- [ ] **AC9: no rule's firing set moves.** For every case in the manifest,
  `segfacet.synth.golden.build_report_for_case(case)`'s verdict and the ordered
  `(rule_id, severity, labels)` tuples of its findings equal
  `tests/test_098_stray_components.py::_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`
  with that constant's `rule_id` / `severity` / `labels` values **unchanged**. A
  numeric value quoted inside a finding's `reason` may be updated to the
  regenerated measurement; a changed, added or removed finding is a hand-back
  (see AC10).

- [ ] **AC10: a moved firing set is recorded and handed back, never absorbed.**
  If AC9 fails for any case, the item stops: one line is appended to
  `docs/aide/insights.md` naming the case, the rule and the measured before/after
  firing sets, and the branch is handed back. No threshold under
  `src/segfacet/heuristics/` is changed to make AC9 pass. Evidenced by the diff:
  no file under `src/segfacet/heuristics/` appears in it, and
  `python .aide/scripts/aide.py scope 143 --base aide/queue-020` exits 0 with no
  path outside this spec's authorised list.

- [ ] **AC11: every regenerator is deterministic run-to-run.** Each of
  `python -m segfacet.synth.corpus --out <tmp>`,
  `python -m segfacet.synth.intensity --out <tmp>`,
  `python -m segfacet.reference.artifact --out <tmp.json>`,
  `segfacet.catalogue.main`, `segfacet.traceability`'s artifact writer and
  `python -m segfacet.golden_evidence` run twice into different destinations in
  one session produces **byte-identical** output (`read_bytes()` comparison — a
  determinism check, not a dependency-version check).

- [ ] **AC12: every regenerated JSON artifact matches its committed copy through
  the item-127 helper.** `tests/corpus/manifest.json`,
  `tests/corpus/intensity/manifest.json`,
  `src/segfacet/reference/reference_default.json`,
  `docs/aide/feature_catalogue.generated.json`,
  `docs/aide/traceability_matrix.generated.json` and
  `docs/aide/golden_evidence.generated.json` each compare equal to a fresh build
  via `segfacet.synth.golden.assert_matches_committed_artifact` (numeric
  tolerance on float leaves, everything else exact).

- [ ] **AC13: every regenerated binary fixture matches its committed copy
  byte-for-byte.** Every `.nii.gz` under `tests/corpus/fixtures/` and
  `tests/corpus/intensity/fixtures/` equals a freshly generated copy on
  `read_bytes()`, under the existing `binary-fixture` allowlist ground.

- [ ] **AC14: no new byte-exact comparison escapes the guard.**
  `tests/committed_artifact_guard.py`'s allowlist gains **no** entry, and
  `tests/test_127_committed_artifact_tolerance.py` reports no violation for any
  test this item adds or edits.

- [ ] **AC15: the two committed Markdown renderings are regenerated and match.**
  `docs/aide/feature_catalogue.generated.md` and
  `docs/aide/traceability_matrix.generated.md` each equal a fresh rendering
  byte-for-byte, and both remain pinned `text eol=lf` in `.gitattributes` (this
  item adds no new committed generated text path, so `aide check`'s
  `.gitattributes` lint gains nothing to report and stays clean).

- [ ] **AC16: the moved/unmoved record exists and covers every artifact.** A new
  `docs/corpus-s-axis-correction.md` carries a dated table with one row per
  committed artifact in the required set (derived, in the test, from the two
  corpus manifests' fixture paths plus a named tuple of the eight non-corpus
  artifacts — see Testing Strategy), and the set of rows equals that required set
  exactly: no artifact missing, no row for an artifact outside it.

- [ ] **AC17: every record row names what was compared and what happened.** Each
  row carries a non-empty `compared by` cell naming the command or helper used
  (e.g. `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()`, or
  `assert_matches_committed_artifact`), a `verdict` cell drawn from exactly
  `{moved, unmoved}`, and a non-empty `detail` cell — for a `moved` row the
  magnitude or nature of the move, for an `unmoved` row why it could not move.

- [ ] **AC18: `reference_verse_v1.json` is unmoved, and that is recorded as
  evidence.** The file is byte-unchanged,
  `tests/test_128_reference_verse_v1_integrity.py` passes with its sha256
  literal untouched, and its row in the record reads `unmoved` with the reason
  that it is built from the real VerSe19 cohort and no synthetic input feeds it
  — the expected result for a real-cohort artifact, not an omission.

- [ ] **AC19: the loader snapshot tracks the regenerated fixtures.**
  `tests/corpus/094_pre_migration_snapshot.json` is re-captured from the
  corrected fixtures so `tests/test_094_tptbox_image_layer.py`'s
  `test_ac3_fixture_loads_byte_identically_to_pre_migration_snapshot` still tests
  the *loader* (its stated purpose: a before/after diff of `load_volume`,
  independent of what the fixtures contain), it still covers all 15 fixture
  entries across both corpora, and the re-capture appears in the record as a
  `moved` row with its reason.

- [ ] **AC20: the full suite is green with nothing disabled.** `pytest` passes,
  every test whose expected value moved carries the regenerated value, and no
  test is deleted, renamed away, skipped or `xfail`-marked to achieve it — the
  collected test-id set on this branch is a superset of the base branch's, and no
  new `skip` / `xfail` marker appears in the diff.

- [ ] **AC21: the report format contract is untouched.**
  `tests/golden/report_format_contract.json` is byte-unchanged and
  `tests/test_126_golden_retirement.py` passes — this item moves feature
  *values*, never the report's key set, key order or float rendering.

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume` (`aide.toml`, `loop.clarify`), so each ambiguity below
was resolved to the most defensible default and recorded here for audit at the
queue boundary.

- **A1: "advances caudally" means ascending label ↔ descending S.** The queue
  one-liner names the direction, not the mechanism. Item 093 pins ascending
  label as head-to-tail (`20 = L1 … 24 = L5`) and item 132's insight measured
  real VerSe19 through `load_volume` at a net S advance of −26 to −364 mm. The
  correction is therefore on the **array side** — label `i` moves to slot
  `n - 1 - i`. Flipping the affine's S sign instead is rejected: `segfacet.io`
  would then permute or flip every array on load, breaking item 116's
  array-identity contract (AC4).

- **A2: the lateral hump is left as a function of the label index.** Because
  `sin(pi * i / (n-1))` is symmetric in `i` and the margins are equal at both
  ends, keeping the hump keyed on `i` while moving the slot to `n - 1 - i`
  leaves the emitted geometry bit-identical and reverses only the labels
  (AC3). The alternative — keying the hump on the slot — produces the same
  array; the chosen form is the smaller diff.

- **A3: the blast radius includes four committed generated artifacts the queue
  entry does not name.** The queue names the geometric corpus, the intensity
  corpus and both reference artifacts. `docs/aide/feature_catalogue.generated.{md,json}`
  (observed-range column, item 124), `docs/aide/traceability_matrix.generated.{md,json}`
  (item 138) and `docs/aide/golden_evidence.generated.json` (item 134) are all
  computed from `catalogue.iter_driver_records()` / `synth.corpus.load_manifest()`,
  i.e. from `build_clean_spine` — so they fall under the entry's own "regenerate
  every committed value the change moves". They are regenerated and recorded here
  rather than left to drift into item 149's re-pointing.

- **A4: `tests/corpus/094_pre_migration_snapshot.json` is re-captured, not
  frozen.** Its digests are of *fixture* bytes, and its purpose (stated in
  `test_094`'s docstring, and `keep` in `golden-decision-table.md` Section 2) is
  to prove `load_volume` is array-identity on these fixtures. Item 116 did the
  same when it moved the stacking axis (commit `b90e0b2`). Freezing it would
  turn a loader test into a fixture-content fence, which item 107 retired as a
  class.

- **A5: `tests/corpus/119_pre_119_digests.json` is not touched.** It pins
  `pipeline.py` bytes and the catalogue's sorted leaf-path set — structure, not
  corpus values — so nothing in it moves.

- **A6: item 131's canonical phrase stays.** `normalised so the sequence
  advances superiorly` (in `features/orientation.py`, `feature_docs.py`,
  `report_schema_v0.json`) describes the *output* of the direction
  normalisation, which is unchanged; only its input direction flips. Editing it
  would break item 131's AC8–AC11 for no gain.

- **A7 (engine 1.37.0): the `.gitattributes` lint has nothing new to report.**
  `aide check` warns when a test's resolved fixture path is uncovered by
  `.gitattributes`. Every committed path this item writes is already pinned
  (`tests/corpus/manifest.json`, `tests/corpus/fixtures/*.nii.gz`,
  `tests/corpus/intensity/**`, `tests/corpus/094_pre_migration_snapshot.json`,
  `src/segfacet/reference/*.json`, the three `docs/aide/*.generated.*` families),
  and `docs/corpus-s-axis-correction.md` is hand-authored prose read with
  `read_text()`, not a byte-reproducible generated fixture, so it needs no pin.

- **A8: no human gate.** The correction is mechanical and its one judgement call
  (a moved firing set) is resolved by handing back, not by deciding. Gate 3 is
  already ✅ Approved and is an input to items 145/146, not to this one. This
  item raises no gate.

## Implementation Steps

1. **Read the generator end to end** (`src/segfacet/synth/clean_gt.py`), and
   confirm the three symmetry facts AC3 depends on: equal S margins at both ends
   (`start2` of the first body is `margin_vox_si`; the last body ends at
   `shape2 - margin_vox_si`), a hump symmetric in `i`, and per-body sizes
   independent of `i`.
2. **Change the slot assignment** in `build_clean_spine`'s per-label loop:
   the `i`-th ascending label occupies slot `n - 1 - i` along axis 2. Change
   nothing else — not `_affine_from_spacing`, not the shape computation, not the
   scan ramp (which is a function of `shape[2]` only and therefore unmoved).
3. **Update the docstring contract** (AC5): state in the module docstring's axis
   paragraph and in `build_clean_spine.__doc__` that ascending labels advance
   caudally (descending S), the way real VerSe input read through `segfacet.io`
   does, while bodies remain stacked along axis 2 per item 116.
4. **Regenerate, in this order, each into a temp destination first and then over
   the committed copy:** `python -m segfacet.synth.corpus`;
   `python -m segfacet.synth.intensity`; `python -m segfacet.reference.artifact`;
   the feature catalogue (`segfacet.catalogue.main` with the committed
   `--json` / `--md` paths); the traceability matrix
   (`python -m segfacet.traceability`, or whatever its committed writer entry
   point is); `python -m segfacet.golden_evidence`. Regenerate each **twice** into
   two temp destinations and diff the bytes before overwriting anything (AC11).
5. **Re-capture `tests/corpus/094_pre_migration_snapshot.json`** (AC19) with a
   throwaway script that mirrors `test_094`'s own reader — for every
   `scan_fixture` / `seg_fixture` in both manifests, load through
   `segfacet.io.load_volume` with the recorded `integer_labels` flag and record
   `{path, integer_labels, shape, dtype, data_sha256, spacing, affine}`. Write
   with `write_bytes` and `\n` newlines (the path is already pinned `text
   eol=lf`). Do **not** commit the throwaway script.
6. **Measure the moved/unmoved record** (AC16–AC18): for each artifact in the
   required set, compare the committed copy against a fresh build with the
   comparison named in AC17, and note the magnitude or nature of any move
   (for a JSON artifact, the pointer of the first differing leaf and its
   before/after values; for a `.nii.gz`, that the bytes moved and which labels
   changed place). Write `docs/corpus-s-axis-correction.md` with the dated table.
7. **Run the full suite and reconcile only what moved.** For each failure decide
   which of two kinds it is: an *expected value that moved* (update the literal
   to the regenerated measurement, keeping the assertion's shape and tolerance)
   or a *direction assumption that is now backwards* (`test_131`'s
   `_PRE_ITEM_NET_ADVANCE_S_MM` and its `net > 0.0` assertion, AC6). Never
   delete, skip or weaken a test (AC20).
8. **Check AC9 last and explicitly** — build every case's report and compare the
   `(rule_id, severity, labels)` tuples against the pre-098 constant. If any
   moved, stop, append the `insights.md` line and hand back (AC10).
9. **Run `python .aide/scripts/aide.py scope 143 --base aide/queue-020`** and
   confirm it exits 0 (AC10's evidence half).

## Authorised paths

**May change:**

- `src/segfacet/synth/clean_gt.py` — the stacking-direction correction (steps 2
  and 3). The only production file this item touches.
- `tests/corpus/fixtures/*.nii.gz` — the regenerated geometric corpus.
- `tests/corpus/manifest.json` — regenerated for proof; expected byte-unchanged
  (it records recipe parameters and expectations, not measurements).
- `tests/corpus/intensity/fixtures/*.nii.gz` — the regenerated intensity corpus.
- `tests/corpus/intensity/manifest.json` — same, regenerated for proof.
- `tests/corpus/094_pre_migration_snapshot.json` — re-captured against the
  corrected fixtures (AC19, assumption A4).
- `src/segfacet/reference/reference_default.json` — built from
  `build_clean_spine` + `paint_clean_scan`, so it goes stale the moment the
  generator changes.
- `docs/aide/feature_catalogue.generated.json` — observed-range column is
  computed from `iter_driver_records()` (assumption A3).
- `docs/aide/feature_catalogue.generated.md` — the rendered form of the same.
- `docs/aide/traceability_matrix.generated.json` — measured per-case firing sets
  come from the corpus.
- `docs/aide/traceability_matrix.generated.md` — the rendered form of the same.
- `docs/aide/golden_evidence.generated.json` — per-case leaf-path counts measured
  over the corpus.
- `docs/corpus-s-axis-correction.md` — **new**: the per-artifact moved/unmoved
  record (AC16–AC18).
- `tests/test_143_s_axis_correction.py` — **new**: this item's test module.
- `tests/*.py` — reconciliation of moved expected values **only**, under the
  fence stated in AC20: a literal expected value may be updated to the
  regenerated measurement and a now-backwards direction assumption may be
  inverted; no test may be deleted, renamed away, skipped, `xfail`-marked or
  otherwise weakened. The sweep in Testing Strategy names the modules known to
  be affected; the breadth of this glob is deliberate (38 test modules read the
  committed corpus) and is fenced by AC20 rather than by enumeration.

**Asserts against:**

- `src/segfacet/heuristics/*.py` — pinned unchanged: AC9's oracle embeds
  `HeuristicConfig`'s live default `max_offset_mm` in the expected `reason`
  text, so a moved threshold breaks it. No rule or threshold changes here
  (AC10).
- `src/segfacet/reference/reference_verse_v1.json` — pinned byte-unchanged by
  AC18 via `tests/test_128_reference_verse_v1_integrity.py`'s sha256.
- `tests/corpus/119_pre_119_digests.json` — pinned unchanged (assumption A5);
  read by `test_119` / `test_120` / `test_123`.
- `tests/golden/report_format_contract.json` — pinned byte-unchanged by AC21.
- `docs/aide/golden-decision-table.md` — the human-signed document; this item
  regenerates its companion, never the signed rows.
- `.gitattributes` — read by AC15 to confirm every regenerated committed path is
  already pinned; no entry is added.

## Testing Strategy

New module **`tests/test_143_s_axis_correction.py`**, one focused test per AC,
plus updates to the modules the sweep below names.

Per-AC tests:

- **AC1/AC2** — build the spine and read per-label centroids straight off
  `np.asanyarray(spine.seg_img.dataobj)` (mean index along
  `synth.axes.si_axis(spine.seg_img.affine)`, converted to mm through the
  affine); assert strict decrease. AC2 parameterises span and spacing.
- **AC3** — the mirror-plus-relabel identity, plus equality of `shape`,
  `spacing`, `affine` and `voxel_counts` against a table of the pre-item values
  for the same arguments (these are generator parameters, not measurements).
- **AC4** — assert `tests/test_116_ras_native_corpus.py` passes (run in the
  suite) and re-assert its two structural properties directly here for the
  default build: stacking axis is 2, and the affine's S/I axis matches it.
- **AC5** — the canonical key phrase in both docstrings; and the absence of any
  claim that ascending labels occupy ascending axis-2 slots.
- **AC6/AC7/AC8** — in `tests/test_131_tangent_direction_normalisation.py`:
  `test_ac6_every_corpus_case_net_advance_positive` becomes the caudal
  assertion (`net < 0.0`) against the regenerated `_PRE_ITEM_NET_ADVANCE_S_MM`;
  `test_ac5_no_corpus_case_tangent_angles_deg_moves` keeps its table and gains
  the `mode4_relabel_swap` tolerance split (AC8), with the residual named in the
  failure message.
- **AC9** — parameterised over the manifest's cases, comparing
  `build_report_for_case`'s ordered `(rule_id, severity, labels)` tuples against
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` (imported, not retyped).
- **AC11** — each regenerator into two `tmp_path` destinations, `read_bytes()`
  equality. Mark the slow ones together so the module stays runnable.
- **AC12/AC13** — `assert_matches_committed_artifact` per JSON artifact;
  `read_bytes()` per `.nii.gz` (allowlisted `binary-fixture`, so the guard stays
  quiet).
- **AC14** — run `tests/committed_artifact_guard.py`'s classifier over this
  item's new/edited test modules and assert no violation and no allowlist growth.
- **AC16/AC17** — parse `docs/corpus-s-axis-correction.md`'s table. Build the
  **required path set** in the test as: every distinct `scan_fixture` /
  `seg_fixture` in `tests/corpus/manifest.json` and
  `tests/corpus/intensity/manifest.json` (repo-relative), plus both manifests,
  plus a module-level tuple of the eight remaining artifacts
  (`tests/corpus/094_pre_migration_snapshot.json`,
  `src/segfacet/reference/reference_default.json`,
  `src/segfacet/reference/reference_verse_v1.json`, the two
  `feature_catalogue.generated.*`, the two `traceability_matrix.generated.*`,
  `docs/aide/golden_evidence.generated.json`). Deriving the corpus half from the
  manifests avoids hand-transcribing 15 paths into a test. Assert set equality,
  then per row: non-empty `compared by`, `verdict in {"moved", "unmoved"}`,
  non-empty `detail`.
- **AC18** — the record's `reference_verse_v1.json` row reads `unmoved`, and
  `tests/test_128_reference_verse_v1_integrity.py` passes unchanged.
- **AC19** — the re-captured snapshot covers all 15 entries and `test_094`'s
  parameterised digest test passes.
- **AC21** — `read_bytes()` of `tests/golden/report_format_contract.json`
  against the value it has at the base commit is *not* how this is asserted (that
  would be a hardcoded fence); instead assert the file is absent from this
  item's diff, checked by the validator via `aide scope`, and that
  `tests/test_126_golden_retirement.py` passes.

Adversarial / edge cases:

- A single-level span (`n == 1`) — the slot formula degenerates to slot 0 and
  must not raise or produce an empty map.
- A two-level span — the smallest case where the reversal is observable.
- Anisotropic and degenerate spacing (`(0.0, 1.0, 1.0)`) through the same paths
  item 116's AC9 guarded, to confirm this change reopens nothing there.
- `curve_amplitude_mm = 0.0` (straight spine) — AC3's mirror identity must still
  hold with no lateral offset.
- A non-contiguous span still raises `FacetInputError` (the validation path is
  untouched).
- Determinism: two `build_clean_spine()` calls in one session return equal
  arrays; two full regenerations are byte-identical (AC11).
- Immutability: `build_clean_spine` mutates no module-level state — a second
  call after a regeneration returns the same array.

**Existing tests to reconcile** (the stale-assumption sweep; the first is
certain, the rest are the candidates a full run must confirm or clear — each is
an *expected value* update under AC20's fence, never a weakening):

- `tests/test_131_tangent_direction_normalisation.py` — **certain**:
  `_PRE_ITEM_NET_ADVANCE_S_MM` holds nine positive values and
  `test_ac6_every_corpus_case_net_advance_positive` asserts `net > 0.0` with the
  message "AC5's table is no longer explained by every case advancing
  superiorly". Both invert (AC6). `_PRE_ITEM_TANGENT_ANGLES_DEG` is expected to
  hold unchanged (AC7/AC8) — if it does not, that is a finding about item 131,
  not a value to retype.
- `tests/test_094_tptbox_image_layer.py` — the 15 snapshot digests (AC19).
- `tests/test_098_stray_components.py` — numeric values quoted inside `reason`
  strings only; the `(rule_id, severity, labels)` half is AC9's oracle and must
  not move. `tests/test_102_stage18_validation.py` imports that constant.
- `tests/test_122_signed_curvature.py` — the signed per-plane arrays are the one
  family whose *sign* can flip under a mirrored curve (the normalisation negates
  the in-plane components); re-measure rather than assume.
- `tests/test_124_observed_range.py`, `tests/test_103_feature_catalogue.py`,
  `tests/test_104_feature_catalogue_drift.py` — observed-range cells and the
  catalogue's fresh-vs-committed comparison.
- `tests/test_040_synthetic_corpus.py`, `tests/test_041_regression_suite.py`,
  `tests/test_042_golden_determinism.py` — corpus round-trip and determinism.
- `tests/test_045_reference_artifact.py`, `tests/test_046_reference_delta.py`,
  `tests/test_049_acceptance_stage6.py`, `tests/test_049_reference_integration.py`,
  `tests/test_063_reference_intensity.py`, `tests/test_090_reference_derived_defaults.py`
  — anything comparing against `reference_default.json`, whose per-label
  intensity statistics do move (the seeded HU texture is fixed in space, so each
  label now covers a different block).
- `tests/test_058_intensity_fixtures.py`, `tests/test_065_intensity_pipeline.py`
  — the regenerated intensity corpus.
- `tests/test_105_golden_decision_table.py`, `tests/test_134_decision_table_evidence_companion.py`,
  `tests/test_138_traceability_matrix.py` — the three generated companions.
- `tests/test_119_curve_formulation.py`, `tests/test_120_leave_one_out_offset.py`,
  `tests/test_123_recalibrate_and_regenerate.py`,
  `tests/test_129_coincident_centroids_and_held_out_floor.py`,
  `tests/test_130_one_closest_point_search.py`,
  `tests/test_132_monotonicity_against_traversal_order.py` — curve-family
  measurements over the corpus. Item 132 made monotonicity direction-agnostic and
  item 130 the closest-point search, so these are expected to pass unchanged;
  they are listed so a failure is read as blast radius, not as a surprise.
- `tests/test_115_stage26_validation.py`, `tests/test_125_stage28_validation.py`,
  `tests/test_135_stage29_validation.py` — stage-validation modules that replay
  corpus measurements.

## Validation

Beyond the suite, observe the corrected corpus directly:

1. `python -m segfacet.synth.corpus --out <tmp>` — then compare `<tmp>` against
   `tests/corpus/` and confirm no difference.
2. `.venv/bin/segfacet run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/clean_control_seg.nii.gz --no-reference --out <tmp>`
   — `--no-reference` is required (CLAUDE.md's Gotchas: the default reference is
   real-VerSe19 and floods the tiny synthetic fixtures with `reference_delta`
   findings). Confirm `pass` with zero findings, and read the human report: the
   per-level table must now show `L1` at the **highest** S and `L5` at the
   lowest.
3. Print the per-label centroid S for `clean_control` and record the two
   endpoints in `docs/corpus-s-axis-correction.md` — the pre-item values were
   `L1 = 27 mm`, `L5 = 187 mm` (measured 2026-08-31, item 131), so the corrected
   pair is the mirror of that.
4. `python .aide/scripts/aide.py scope 143 --base aide/queue-020` — exits 0, no
   path outside the authorised list, nothing under `src/segfacet/heuristics/`.
5. `.venv/bin/python -m pytest --collect-only -q` on this branch and on
   `aide/queue-020`, and confirm this branch's collected test-id set is a
   superset of the base's (AC20's "nothing disabled" half).

No `[validation]` profile is needed: every step runs in the plain project venv
with no optional dependency, so there is no ❓ Unverified downgrade path.

## Dependencies

None blocking. This item lands first and alone in queue-020 by the queue's
prioritisation, and depends only on work already merged: item 093 (ascending
label = head-to-tail), item 116 (axis 2 is S/I; operators resolve axes from the
affine), items 130/131/132 (the closest-point search, the traversal-direction
normalisation and traversal-ordered monotonicity that make a caudal-advancing
corpus read correctly), and item 127 (the committed-artifact comparison helper
and its guard).

**Downstream:** items 144–151 all depend on this one — items 145 and 146 author
expected firing sets that must be measured on the corrected corpus, item 149's
matrix scores expected against measured, and Stage 20's later specificity
ratchet pins its baseline after this item, not before.

## Decisions & Trade-offs

- **Implementation matches A1/A2 exactly.** `build_clean_spine`'s per-label
  loop now computes `slot = n - 1 - i` and places the `i`-th ascending label's
  body at `start2 = margin_vox_si + slot * (body_vox_si + gap_vox_si)`; the
  lateral hump (`amplitude * sin(pi * i / (n - 1))`) stays keyed on `i`,
  unmodified. Verified directly (AC3): mirroring the default build's array
  along axis 2 and relabelling `labels[i] -> labels[n-1-i]` reproduces the
  original array bit-for-bit, and `shape`/`spacing`/`affine`/`voxel_counts`
  are byte-identical to the pre-item generator's output for the same
  arguments.

- **Canonical docstring phrase.** `ascending labels advance caudally` (all
  lowercase, matching `_CANONICAL_KEY_PHRASE` in the test module exactly) is
  used verbatim in both `clean_gt.py`'s module docstring and
  `build_clean_spine.__doc__`. Both docstrings' first draft accidentally wrote
  `ascending axis-2 positions` as a *negation* ("do not occupy ascending
  axis-2 positions") — but AC5's test does a blunt substring check with no
  regard for negation, so that phrasing failed the forbidden-phrase assertion.
  Reworded to state the same fact without the forbidden substring ("the label
  order and the array-axis-2 slot order run opposite each other").

- **AC9 held with no rule/finding change (measured, not assumed).** Built
  every corpus case's report via `build_report_for_case` and compared
  `(rule_id, severity, labels)` tuples — plus every finding's `reason` text —
  against `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`: all nine cases matched
  exactly, including `reason` strings that quote numeric measurements. No
  `insights.md` hand-back entry was needed (AC10 is a no-op on this branch).

- **The full "existing tests to reconcile" sweep was measured, not assumed.**
  Every candidate table the spec's Testing Strategy names (`test_094`'s 15
  digests; `test_098`'s two `_PRE_098_*` tables; `test_102`'s block-C
  hardcoded metric values, which call `build_clean_spine` directly;
  `test_120`'s AC23/AC24 offset and sensitivity values; `test_122` — no
  hardcoded corpus tables, presence/determinism checks only;
  `test_123`'s AC44/AC45 threshold and interior-ceiling values;
  `test_124`/`test_103`/`test_104` — no hardcoded corpus-value literals;
  `test_045/046/049/063/090` — no hardcoded corpus-derived literals, or
  compared via `assert_matches_committed_artifact` against the regenerated
  `reference_default.json`; `test_058/065` — no hardcoded literals;
  `test_105/134/138` — SHA/leaf-path-set pins unrelated to corpus values;
  `test_119/129/130/132` — `_PRE_119_DIGESTS` (leaf-path-set, unaffected),
  `_PRE_129_*`, `_PRE_ITEM_U_VALUES`, `_PRE_ITEM_OBSERVED_SUMMARY`,
  `_PRE_ITEM_STATUS_OVERRIDES`; `test_115/125/135` — no hardcoded
  corpus-derived literals, or (`test_135`'s AC14 table) derived from a
  synthetic fixture independent of the corpus) was measured against the
  corrected corpus. `test_131`'s `_PRE_ITEM_NET_ADVANCE_S_MM` table and its
  `net > 0.0` assertion needed updating (AC6), and `_PRE_ITEM_TANGENT_ANGLES_DEG`
  (the direction-normalised overall tangent angle) is genuinely unmoved, as
  item 131's traversal-direction normalisation and item 132's
  traversal-order-agnostic monotonicity predict.

  **Correction (round 2, 2026-09-03):** the claim that "every other
  candidate's values are numerically unmoved" was wrong for three tables the
  original sweep either missed or mismeasured — the validator caught it via
  three failing tests, and completing the sweep by that same failure class
  found the same defect had gone unreported in a fourth spot the per-case
  assertion loop never reached:
  - `test_121_tangent_orientation.py`'s AC5 `expected` list (`coronal_deg` for
    `clean_control`'s five levels) — this table was **never named** in the
    original sweep at all. `coronal_deg` is the signed per-level R-S tilt
    (unlike `_PRE_ITEM_TANGENT_ANGLES_DEG`'s direction-normalised magnitude),
    so it flips sign under the S mirror: `[8.1644, 4.0746, 0.0000, -4.0746,
    -8.1644]` → `[-8.1644, -4.0746, 0.0000, 4.0746, 8.1644]`.
  - `test_131_tangent_direction_normalisation.py`'s
    `_PRE_ITEM_OTHER_CURVATURE_FIELDS` table — every case's
    `coronal_tangent_angles_deg` and `sagittal_tangent_angles_deg` entries
    (the signed per-level component breakdown, not the normalised overall
    angle in `_PRE_ITEM_TANGENT_ANGLES_DEG`) are exactly sign-flipped, for
    all nine cases, not only `clean_control`; `total_curvature_deg`,
    `coronal_curvature_deg`, `sagittal_curvature_deg` and `curvature_plane`
    (unsigned magnitudes/labels) are genuinely unmoved. The per-case `for`
    loop this test runs stops at the first mismatch, so only `clean_control`
    surfaced as a validator failure even though all nine entries were stale.
  - `test_132_monotonicity_against_traversal_order.py`'s `_PRE_ITEM_U_VALUES`
    table — `mode6_crop_at_border`'s middle `u_value` moved by ~4.77e-8
    (`0.500000024` → `0.499999976`), outside the test's `abs=1e-9` tolerance;
    every other case's `u_values`, including `mode6`'s other four entries, are
    unmoved within that tolerance and needed no change.

  The lesson: a *signed component* of a normalised quantity (a per-axis
  tangent angle, a per-level tilt) is not protected by the same
  direction-normalisation invariant that protects the normalised quantity
  itself, and a per-case assertion loop that stops at the first failure can
  hide identical staleness in every later case. See
  `docs/corpus-s-axis-correction.md`'s "Round-2 reconciled tests" section for
  the full before/after values.

- **`reference_default.json`, `feature_catalogue.generated.{json,md}` moved
  by floating-point noise only (~1e-9 relative), not by a substantive shift.**
  Per-label `spline_offset_mm` distribution statistics and the catalogue's
  observed-range `minimum` for `per_label_offsets[].offset_mm` /
  `offset_voxel` moved in the last few significant digits — the same
  magnitude as the per-case `offset_mm` noise directly measured against
  `mode5_remove_level` (all differences < 1e-9 absolute, well inside
  `assert_matches_committed_artifact`'s numeric tolerance). Recorded as
  `moved` in `docs/corpus-s-axis-correction.md` rather than `unmoved` because
  the bytes did change and the record is about what happened, not about
  whether the move is "big enough to matter."

- **`traceability_matrix.generated.{json,md}` and `golden_evidence.generated.json`
  are unmoved.** Both are computed from rule/feature wiring structure and
  per-case leaf-path *counts* respectively — neither depends on which S
  coordinate a label sits at, and AC9 confirms no case's firing set moved, so
  both regenerated byte-identical to the pre-item committed copy.

- **`tests/corpus/094_pre_migration_snapshot.json` re-capture used a
  throwaway script (not committed)** that mirrors `test_094`'s own reader
  exactly (`segfacet.io.load_volume` per entry, `sha256` of
  `np.ascontiguousarray(data).tobytes()`), writing with `write_bytes` and
  `json.dumps(..., indent=2, sort_keys=True) + "\n"` to match the committed
  file's existing serialisation. 14 of 15 entries' digests moved (every
  segmentation fixture in both corpora, plus every intensity scan whose
  seeded texture is painted at fixed voxel positions); the 15th
  (`corpus/fixtures/base_scan.nii.gz`, a ramp over `shape[2]` only) is
  byte-unchanged, consistent with its own `unmoved` corpus-fixture row.
