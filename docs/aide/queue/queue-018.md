# FACET — Work Queue 018
> **Status:** ✅ Completed — superseded by queue-019 (2026-09-02).

> **Created:** 2026-08-30
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 29**; supersedes the completed [`queue-017.md`](queue-017.md)
> (Stage 28, closed 2026-08-30).

---

## Scope of this queue

Delivers roadmap **Stage 29 — Golden Retirement & Test-Artifact Hygiene**
(G2, G7) in full: ten items covering eleven deliverables plus the stage
validation, under `loop.queue_cap = 10`. Two pairs of deliverables share an
item because they change the same surface and are verified by the same kind of
test: D4 and D5 are both small-centroid-count behaviour in the spline-offset
layer (item 129), and D9 and D10 are both dependency/script maintenance with no
feature semantics (item 133). Every other deliverable is its own item.

This is a remediation stage in the Stage-26 mould: every item has a named
location and a measured cause, and **the stage does no discovery**. An item
that turns into an investigation should hand back rather than widen.

**Why the retirement comes first.** Items 119/120/123 each regenerated nine
snapshot goldens plus both reference artifacts and touched ~8 pinning test
files, and three of those items' test-writing passes reintroduced byte-exact
comparisons against committed float-carrying artifacts that only PR #56's CI
matrix caught (~1 ULP float drift across numpy versions and platforms). All 11
whole-record snapshots are maintainer-dispositioned *retire* in
[`../golden-decision-table.md`](../golden-decision-table.md) (signed
2026-07-28, item 106); executing that disposition (item 126) shrinks the
regeneration surface of everything after it. Concretely: item 129's boundary
move changes `mode5_remove_level` (a 4-level fixture), item 132 changes
`mode4_relabel_swap`'s `is_monotonic`, and item 133's dependency bump has the
golden corpus as its regression surface — with the snapshots gone, none of
those regenerates anything.

**Re-measured 2026-08-30 while scoping this queue** (so items start from the
current state, not the roadmap's provenance text):

- `fit_centroid_spline` **already** raises a descriptive `ValueError` naming
  the coincident coordinate and both levels (item 119, AC16) — the roadmap's
  "propagates SciPy's bare `Invalid inputs.`" predates that. What remains for
  D4 is one level up: a label map in which two labels share a centroid (one
  label painted inside another) makes `extract_feature_record` raise, so
  `segfacet run` produces a traceback instead of a report. That is item 129's
  actual D4 gap.
- The 4-centroid silent zero reproduces exactly: on a 6 mm-amplitude 4-level
  curve `compute_leave_one_out_spline_offsets` returns
  `[0.0001, 0.0, 0.0, 0.0001]` mm; the same generator at 5 levels returns
  `[0.06, 0.18, 0.38, 0.18, 0.06]` mm. `_MIN_LEVELS_FOR_HELD_OUT` is `4`
  (`features/spline_offset.py:161`).
- `pip show tptbox` in the project venv reports
  `License: GNU AFFERO GENERAL PUBLIC LICENSE v3.0` for the pinned 0.7.5.

**Prioritisation.** Item 126 first, for the reason above. Item 128 is small
and should land before item 127, so that 127's enforced allowlist names the
`reference_verse_v1` byte pin at its final home rather than being edited
twice. Items 129, 131 and 132 are independent behaviour changes in the spline
layer, each carrying its own fails-before-the-fix regression test; item 130 is
a pure consolidation of that same layer and is best landed before 132 so the
monotonicity change is made against one closest-point implementation, not
three — but `aide claim` may offer them in any order and nothing breaks if it
does. Items 133 and 134 are independent of everything except 126. Item 135
closes the stage.

**Scope fence for the whole queue.** Retirement means deletion with the four
named replacements in place — **not** regeneration. An item that regenerates a
snapshot golden "on the way out" has done the exact move the disposition
forbids. Signed text (`golden-decision-table.md`'s dispositions and reasoning,
`feature_docs.STATUS_OVERRIDES`) is never rewritten from inside an item: a
row's execution is recorded as a dated note beside it, and a live count moves
out of the signed document rather than being refreshed inside it (item 134).

**Numbering.** Continues at the next free integer: **126–135**.

---

## Work items

### Item 126: Execute the golden retirement

Delete the 11 whole-record snapshot goldens the maintainer dispositioned
*retire* on 2026-07-28 — the nine `tests/corpus/golden/*.json` reports (item
042) and `tests/golden/016_features_report.json` /
`tests/golden/022_stage3_report.json` (items 016/022) — and land the four
replacements each row of [`../golden-decision-table.md`](../golden-decision-table.md)
specifies: (i) intra-run determinism stays covered by the existing run-to-run
tests (`test_042`'s AC4/AC12, `test_098`'s AC16, `test_016`/`test_022`'s
repeated-serialisation tests), none of which need the committed file; (ii)
schema validity re-points at a freshly built report
(`test_042_golden_determinism.py::test_ac7_…` validates
`build_report_for_case` output against `report_schema_v0.json`); (iii) the
load-bearing "verdict/findings unchanged" use moves to a narrow
verdict+findings shape expectation of the `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`
kind, pinning no feature values so it survives a feature retune; (iv) the two
`tests/golden/` snapshots' report-*format* guarantees (key order, key set,
float formatting) move to one small hand-constructed, feature-value-free
fixture shared by `test_016` and `test_022` — and that fixture must not
inherit `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`'s
write-and-skip defect (a missing file currently self-heals instead of
failing). Every consumer the table's "Used by" column lists (`test_042`,
`test_089`, `test_090`, `test_094`, `test_098`, `test_102`) is re-pointed or
retired accordingly. Record execution in the decision table as a dated note
per row, never by rewriting the signed disposition; reconcile
`test_105_golden_decision_table.py` and `test_111_golden_guard.py` with rows
whose paths no longer exist. **Nothing is regenerated on the way out**, and
the corpus `manifest.json` and `.nii.gz` fixtures stay — only the
whole-record report snapshots go. *Testable:* the 11 files are absent from
the tree; the suite is green with the determinism, schema-validity,
verdict+findings-shape and format-fixture replacements each present and
named; the write-and-skip defect is gone (deleting the new format fixture
fails loudly); `git log` shows no regeneration commit for the retired paths.

### Item 127: Tolerance by construction for committed-artifact comparisons

Make "fresh output vs committed artifact" reach for numeric tolerance by
construction rather than by reviewer vigilance. Two parts. First, a shared
comparison helper (a test utility beside `reports_close`, whose name says it
compares against a *committed* artifact) that applies `reports_close`-style
numeric tolerance to floats while comparing structure, keys, strings, bools
and ordering exactly — item 078's relaxation, made the only path. Second, a
guard test extending `tests/test_111_golden_guard.py`'s hand-surveyed
`_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` into an **enforced allowlist**: a test
that byte-compares freshly generated output against a committed
float-carrying artifact outside the allowlist fails with a message naming the
helper. The spec carries the rule for what legitimately stays byte-compared,
recorded from item 124's PR #56 fix: an artifact reporting a raw float
measurement alongside its own "meaningfully nonzero" threshold must clamp
sub-threshold noise to a fixed sentinel at the serialisation boundary
(`segfacet.observed_range.emission_range` is the shipped example —
quantisation cannot stabilise cancellation-scale noise); and a spec that
changes a feature the reference artifact aggregates must survey every
consumer mechanically (`grep -l build_and_write_default tests/`), not by
hand-listing. Lands after item 126, so the allowlist describes the
post-retirement inventory, and after item 128, so it names the
`reference_verse_v1` pin at its relocated home. *Testable:* on a scratch
branch, a deliberately added `read_bytes()` comparison of fresh output against
`reference_default.json` fails the guard with the helper's name in the
message; the helper passes a report differing from its committed copy by 1 ULP
in a float and fails one differing in a key, a string, a bool or list order;
every existing tolerance comparison in `tests/` goes through the helper or is
on the allowlist with a one-line reason.

### Item 128: Relocate the `reference_verse_v1` integrity pin and rename the `test_102` fence header

Two located hygiene defects routed 2026-08-25.
`tests/test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged`
pins `src/segfacet/reference/reference_verse_v1.json`'s bytes under an
item-098 scope-fence name; the invariant is legitimate — a released production
artifact must not change silently — but it belongs in a test named for the
artifact, beside `reference/artifact.py`'s tests, with its purpose stated in
the docstring. Carry its `.gitattributes` `text eol=lf` pin across
deliberately: engine 1.19.0's lint resolves fixture paths through the test's
AST and cannot see one reached through a helper function, so the absence of a
warning after the move proves nothing (see `CLAUDE.md` Gotchas). And
`tests/test_102_stage18_validation.py:826`'s `# AC24: the scope fence -- no
production code changed by this item` header sits over a legitimate intra-run
determinism assertion; renaming the header to say what the test checks is the
whole fix. Small, and best landed before item 127 so the enforced allowlist
names the pin once, at its final location. *Testable:* the byte pin exists
under the new name and location and still fails when a byte of
`reference_verse_v1.json` changes; `test_098` no longer carries it; the
`.gitattributes` pin covers the path; `test_102`'s header names the
determinism property; `aide check` reports no new warning.

### Item 129: Coincident centroids in the pipeline, and the 4-level held-out boundary

Two small-centroid-count defects in the spline-offset layer. **Coincident
centroids (D4).** `fit_centroid_spline` already raises a descriptive
`ValueError` naming the coincident coordinate and both levels (item 119,
AC16); what does not exist is graceful degradation one level up. Measured
2026-08-30: a label map in which one label is painted inside another (so two
labels share a centroid) makes `extract_feature_record` raise, and `segfacet
run` produces a traceback instead of a report. Make the pipeline degrade the
way the ≥2-centroid guard already does for one label — Stage 3 absent or
marked degenerate, with the cause recorded in the record so a rule or the
report can name it — rather than losing the whole case, and let item 122's
substituted 1e-6 mm near-coincident adversarial fixture
(`test_122_signed_curvature.py::test_adv_all_centroids_coincident_no_crash_finite`)
become the real all-coincident case. **The 4-level silent zero (D5).**
`compute_leave_one_out_spline_offsets`'s `_MIN_LEVELS_FOR_HELD_OUT = 4`
boundary is one too low: with four points and `k = 3` the down-weighted
refit interpolates and every held-out offset reads `0.0` (measured on real
`sub-verse065`, and reproduced 2026-08-30 on a synthetic 4-level curve:
`[0.0001, 0.0, 0.0, 0.0001]` mm against `[0.06, 0.18, 0.38, 0.18, 0.06]` mm at
five levels), so a 4-level field of view cannot raise a `mislabel` offset
finding. Move the boundary to `< 5`, state in the module docstring why five
is the floor, and rebuild the reference distributions it affects with
`scripts/rebuild_verse_reference.py` — any VerSe subject with exactly four
levels moves from zero to a real offset — confirming that `mislabel`'s
`max_offset_mm` (calibrated by item 123) still sits between the clean and
displaced distributions. Depends on item 126: `mode5_remove_level` is a
4-level fixture and its retired snapshot would otherwise need regenerating.
*Testable:* the nested-label map yields a report (through `extract_feature_record`
and `segfacet run --no-reference`) that names the coincident levels; the
all-coincident fixture exercises the real path; a 4-level curve yields
non-degenerate held-out offsets and a 3-level one still takes the in-sample
fallback; both regression tests fail before the fix; the rebuilt
`reference_verse_v1.json` differs only in the affected subjects' offset
distributions.

### Item 130: One closest-point search, one in-sample fit

The coarse-scan-plus-`minimize_scalar` closest-point search exists three
times with no link between them — `features/spline_offset.py` (line ~254),
`features/consistency.py::_find_closest_u` (line 128) and
`scripts/compare_curve_candidates.py` (line ~233) — and the pipeline fits the
identical in-sample spline twice per case: `pipeline.py:156`'s curvature fit
and `compute_leave_one_out_spline_offsets`'s internal reference fit. One
implementation of the search, owned by the spline layer and imported by the
other two callers (the script included, so its published measurements are
made by the shipped code); one in-sample fit per case, passed to every
consumer. This is a consolidation, not a behaviour change: every existing
value-level assertion in `test_017`–`test_023`, `test_119`–`test_122` and
`test_125` must pass unchanged, which is the evidence that nothing moved.
Best landed before item 132 so the monotonicity change is made against one
implementation. *Testable:* exactly one definition of the search remains
(`grep -rn minimize_scalar src/ scripts/` finds one call site); a test counts
`fit_centroid_spline` calls per `extract_feature_record` and asserts the
reduced number; `docs/spinal-curve-model.md`'s quoted measurements still
reproduce via `scripts/compare_curve_candidates.py`.

### Item 131: Normalise `tangent_angles_deg[]` for traversal direction

`compute_spine_curvature`'s `tangent_angles_deg[]` is the unsigned angle
between each tangent and `+S`, so it reads ~175° per level on a
cranial-first centroid sequence and ~5° on a caudal-first one — the same
spine, two readings — latent only because every committed fixture happens to
advance superiorly. Item 122 already established a direction convention for
its signed per-plane arrays (`coronal_tangent_angles_deg`,
`sagittal_tangent_angles_deg`); normalise the unsigned array (and
`inter_tangent_angles_deg` if it inherits the same sensitivity) to that
convention so the record carries **one** tangent-angle convention, and state
it once where the field is defined. `orientation.py:475` currently records
these two arrays as deliberately unaffected by item 122 — that note is
superseded here. The committed catalogue (`docs/aide/feature_catalogue.generated.*`)
regenerates if its `computation` text changes; the corpus fixtures'
values do not move because they already advance superiorly. *Testable:* a
fixture and its reversed copy produce identical `tangent_angles_deg[]` and
`inter_tangent_angles_deg[]`; the regression test fails before the fix; the
convention is asserted, not only documented; the catalogue drift test
(`test_104`) still agrees.

### Item 132: Judge monotonicity against the smoothed fit so mode 4 fires

Stage 28 asserts a smoothed fit detects the mode-4 label swap via
`stage3.monotonic_consistency.is_monotonic == False`, but no queue-017 item
owned `features/consistency.py`, and item 125's replay measured the criterion
unmet: `mode4_relabel_swap` reads `is_monotonic == True` with zero
`non_monotonic_pairs`, pinned by
`tests/test_125_stage28_validation.py::test_ac7_mode4_relabel_swap_is_monotonic_pinned_true`.
Make `compute_monotonic_consistency` judge the ordering of the centroids'
closest-point parameters along the smoothed curve (the same
`closest_u` the offset layer computes) rather than a construction that
follows the swapped pair, so the swapped levels appear in
`non_monotonic_pairs`. Then close the loop: flip item 125's pin (authorised
here, with the item number in the assertion message), move
`mode4_relabel_swap` in `tests/corpus/manifest.json` from
`detection="reconstructed_record"` to `detection="pipeline"` if the finding
now reaches `run_qc` through the `sequence` rule, and confirm `clean_control`
and the real VerSe cohort do not start reporting non-monotonic pairs (a
scoliotic spine is still monotonic along its own curve). The Stage 28
acceptance half itself is ticked by item 135's replay, not here. *Testable:*
`mode4_relabel_swap` yields `is_monotonic == False` through
`extract_feature_record` with the swapped pair named; `clean_control` and
every real VerSe19 subject stay `True`; the regression test fails before the
fix; `manifest.json` regenerates byte-identically run-to-run.

*Correction (2026-09-01, from insights.md's item-132 entry of 2026-08-31):* the
mode-4 finding does not reach `run_qc` "through the `sequence` rule" —
`heuristics/sequence.py::SequenceRule` reads `relationships.out_of_order_labels`
and never touches `monotonic_consistency`. The consumer of
`stage3.monotonic_consistency.non_monotonic_pairs` is
`heuristics/mislabel.py::MislabelRule`'s Detector B (`rule_id == "mislabel"`),
which is what `tests/corpus/manifest.json` has always recorded as mode 4's
`expected_rule_ids`; item 132's spec carries the same correction, and roadmap
Stage 29 D8 names no rule.

### Item 133: `tptbox` ≥ 0.7.6 and `refresh_reference.py --verse-cohort`

Two maintenance items with no feature semantics. **The dependency (D9).**
The pinned `tptbox==0.7.5` wheel declares `GNU AFFERO GENERAL PUBLIC LICENSE
v3.0` in its metadata (measured 2026-08-30 via `pip show`) while TPTBox's
`LICENSE` is Apache-2.0; upstream fixed the metadata in v0.7.6 (TPTBox PR
#119). Bump `pyproject.toml` and `constraints.txt` together, confirm
`test_093_tptbox_label_convention.py` and `test_094_tptbox_image_layer.py`
still pass on the new wheel, and record the observed licence string. Its
regression surface was the golden corpus, which is why this waits for item
126. **The script (D10).** `scripts/refresh_reference.py --verse-cohort` has
never worked: it hands the cohort root to `ingest_cohort`, which lists one
directory non-recursively and hardcodes `_scan.nii.gz` siblings —
incompatible with VerSe's layout — so the wrapper records `verse-build:
failed` by construction (`refresh_reference.py:217-246`). Either delegate the
mode to item 123's `scripts/rebuild_verse_reference.py`, which does build the
real artifact from the local cohort, or retire the flag and its `verse-build`
step with a pointer to that script; the spec picks one and says why, and the
script's docstring stops advertising a mode that cannot run. *Testable:*
`pip show tptbox` reports a non-AGPL licence and the version is ≥ 0.7.6 in
both pin files; the tptbox-gated tests run (not skip) and pass; a test drives
`refresh_reference.py` with `--verse-cohort` against a two-subject
VerSe-layout fixture and asserts either a successful build record or a clear
retired-mode error — never `verse-build: failed`.

### Item 134: Generate the decision table's measured counts into a companion artifact

[`../golden-decision-table.md`](../golden-decision-table.md)'s `N/M leaf paths
unwired` evidence cells are live values off `catalogue.build_catalogue()`
(`tests/test_105_golden_decision_table.py:346-377` parses and re-derives
them), so every feature-adding item (106, 110, 122) has edited a human-signed
document to refresh a count while asserting that no judgement moved. Generate
the measured counts into a small companion artifact the signed document
references — generated like the catalogue, never hand-maintained,
byte-reproducible, written with `\n` bytes and pinned `text eol=lf` in
`.gitattributes` — and re-point `test_105`'s drift assertion at the
companion, so a count refresh never touches signed text again. The signed
table's cells then carry a stable pointer, not a number. Lands after item 126
so the companion describes the post-retirement rows. *Testable:* the companion
regenerates byte-identically run-to-run; `test_105` compares the companion,
not the table, against `build_catalogue()`; a deliberately stale companion
fails the drift test while the signed table is untouched; `aide check`'s
`.gitattributes` lint is clean for the new path.

### Item 135: Validate stage 29: Golden Retirement & Test-Artifact Hygiene

Replay Stage 29's acceptance end-to-end rather than re-running the unit
suite. Confirm all 11 retired snapshots are absent, each of the four named
replacements is present and named per row, and `git log` shows no
regeneration of a retired path between queue-018's first commit and the
retirement (**G7**). On a scratch branch, add a byte-exact comparison of
fresh output against a committed float-carrying artifact and confirm item
127's guard fails it naming the helper; discard the branch (**G7**). Run
`mode4_relabel_swap` through `extract_feature_record` and through `segfacet
run --no-reference` and confirm `is_monotonic == False` with the swapped pair
named, and tick Stage 28's unticked mode-4 acceptance half in `progress.md`
with that evidence sentence (**G2**). Confirm a 4-level field of view yields
non-degenerate held-out offsets, that the nested-label map yields a report,
and that `pip show tptbox` in the venv reports a non-AGPL licence. For every
fixed defect (items 128–134), check out the commit before its fix and confirm
its regression test fails there — the "fails before the fix" claim is
verified, not assumed (**G7**). Confirm the suite is green on a **fresh clone
in a different directory**. Then update `progress.md`: tick Stage 29's three
acceptance criteria against what was actually exercised, and flip any
Environment-Gated Capability Verification row this stage affects to ✅
Verified where the environment allows (`python .aide/scripts/aide.py env
--profile <name>`), otherwise record why it stays ❓ Unverified. *Testable:*
each acceptance criterion is ticked with a recorded evidence sentence naming
what was run; the fresh-clone suite is green; `aide check` reports no new
warnings.

---

## Current state (2026-08-30)

Generated on completion of [`queue-017.md`](queue-017.md), which delivered
**Stage 28 — Spinal Curve Model: Formulation, Offset & Orientation** (items
118–125, all ✅; three of five acceptance criteria ticked, the mode-4 half
and the scoliotic-case criterion left honestly unticked with their evidence).
Opens **Stage 29 — Golden Retirement & Test-Artifact Hygiene**, scoped
2026-08-30 at the queue-017 boundary triage. Run order from here:
**29 → 20 → 27 → 21 → 16**. Stage 20 (traceability matrix + specificity
ratchet) is authored as a queue only after this stage lands, because items
126, 131 and 132 change the surfaces it audits and the baseline it pins.
Stage 16 remains held by two human gates awaiting a decision — real
segmenter output handed over to this repo, and access to the curated
challenging-case source data. Stage 11 stays ⏸️ Deferred and Stage 15 ❌
Excluded.
