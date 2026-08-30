<!--
  AIDE insight inbox — the compound-engineering capture point. Copy this file
  VERBATIM (comment included, no slots to fill) to docs/aide/insights.md the
  first time an insight needs a home.

  Any role, at any time: when you learn something true but OUT OF SCOPE for
  your current task, append ONE line here and return to your task. Capturing
  is cheap and always allowed; ACTING on it out of scope is forbidden.

  Entry shape (checked by `aide check`, non-blocking):
    - [ ] <type> — <one line> *(<where it came from>, YYYY-MM-DD)*

  The date is required; the provenance before it is free-form and may be
  omitted. Conventional spellings, worth following so a reader can scan them:
    *(item 099, 2026-07-26)*        captured while working one item
    *(items 099-101, 2026-07-27)*   a finding that spans several
    *(queue-014, 2026-07-26)*       queue planning or spec-authoring, before
                                    any item exists
    *(2026-07-26)*                  no item or queue to name
  Write whichever is honest — never bend one to fit, since the line below is
  immutable and a squeezed provenance can never be corrected.
  Types:
    knowledge  — true fact worth documenting (docs, CLAUDE.md, conventions)
    defect     — something is wrong and needs a fix item
    gap        — something is missing and needs planning (roadmap/queue)
    automation — a recurring manual/agent action that deterministic code
                 could replace (a CLI verb, a script)
    framework  — belongs to AIDE itself, not this project; triage hands it
                 over to the framework repo ([framework] repo in aide.toml)

  Triage routes each entry to its destination, then ticks it in place with a
  pointer:
    - [x] <type> — <one line> *(item NNN, YYYY-MM-DD)* → <where it landed>
  Triage happens at the queue boundary (feedback loop) for every type that
  lands in this project; a `framework` entry leaves for another repo's issue
  tracker and may be triaged on capture or on demand.

  The captured claim is IMMUTABLE — never reworded, reordered or deleted, not
  even when it turns out to be wrong (the wrongness is the record). Ticking the
  checkbox is the one in-place edit. Everything that happens to an entry AFTER
  triage goes in an appendable status trail: dated lines, indented under the
  entry, newest last.
    - [x] framework — <the original claim, never touched> *(2026-08-20)*
      - **2026-08-20** → aide-loop issue #50
      - **2026-10-11** → resolved in engine 1.16.0
-->
# Insight Inbox

_Entries below, newest last._

- [x] gap — `out/` is not in `.gitignore`, yet it is the `--out` target in the reproduction commands the repo itself documents (`docs/spinal-curve-model.md`'s `scripts/compare_curve_candidates.py --out out/curve-candidates`, and `docs/reference-build.md`'s rebuild recipe). Following either recipe leaves an untracked `out/` behind, after which every subsequent `python .aide/scripts/aide.py sync --item NNN` refuses with "working tree not clean -- commit or stash before starting: ?? out/" and the session's deterministic preflight stalls until someone hand-removes it. Encountered live while starting item 125 (leftovers from item 123's VerSe rebuild, dated 2026-08-29). Either `.gitignore` should cover `out/` or the documented recipes should target a scratch path outside the repo *(item 125, 2026-08-30)* → fixed — out/ added to .gitignore at the 2026-08-30 feedback-loop triage

- [x] framework — `aide check --queue NNN`'s pin-vs-edit check (`item A may change X, which item B pins as X under Asserts against`) does not discount items that are already ✅ and merged, so it fires structurally on **every** stage-validation item. A `Validate stage N` item exists precisely to pin the artifacts its stage's items produced, so its `Asserts against` list necessarily collides with their `May change` lists — item 125 draws 14 such errors from items 118-123, all inert, and neither remedy the message offers is correct (widening the pin drops the artifacts the item exists to observe; narrowing the earlier edits is impossible, they are shipped). Same root cause as the dependency-cycle entry above (2026-08-29): the cross-spec checks reason over spec declarations without consulting `progress.md` status. A completed item can no longer "land" after anything *(item 125, 2026-08-30)* → aide-loop#106

- [x] defect — `docs/spinal-curve-model.md`'s "Revisions to apply when item 119 implements this" section claims that switching the `smoothing_spline` candidate from raw `splprep` to the shipped `fit_centroid_spline` (`make_splprep`, identical `s = n_points`) leaves "every value in `## Measurements` still reproduces" — measured false for one row. Re-running `scripts/compare_curve_candidates.py --verse-cohort dataset-verse19training` on 2026-08-30 reproduced 15 of the 16 documented keys exactly (within the stated 0.001 mm tolerance, including the count-valued determinism row), but `candidates.smoothing_spline.verse_scoliotic.max_pass_through_mm.leave_one_out` measured `20.683092` mm against the documented `21.073357` mm — a 0.390 mm divergence, ~400x the stated tolerance. `make_splprep` is SciPy's newer, independent smoothing-spline implementation (not a `splprep` wrapper with the same numerics), so an identical `s` value does not guarantee an identical fit for every input; this particular leave-one-out fit over one of the 17 selected real scoliotic cases is evidently sensitive to that difference even though every other measured key (including three other `verse_scoliotic` rows on the same 17-case selection) reproduced to within 1e-6 mm. Immaterial to the shipped `max_offset_mm = 13.0` (item 123 superseded the original 25.0 mm envelope this figure fed with its own, differently-derived interior-only ceiling), but the document's specific "still reproduces" claim is not true and should be corrected or re-measured rather than cited as-is *(item 125, 2026-08-30)* → docs/spinal-curve-model.md §'Revisions to apply…' now carries the dated 2026-08-30 correction with the measured divergence

- [x] defect — `segfacet run`'s **default** invocation (no `--reference`/`--no-reference` flag) enables reference mode against the bundled real-VerSe19 `reference_verse_v1.json` (item 090's default), so a real end-to-end CLI run on any of the corpus's tiny synthetic box fixtures (30x25x25 mm vertebrae, versus real anatomy) reports dozens of `bounds` and `reference_delta` findings and a `flagged-for-review` verdict even for `clean_control_seg.nii.gz` — not the "zero findings, pass verdict" the corpus/stage documentation describes for a clean case. Measured 2026-08-30: `segfacet run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/clean_control_seg.nii.gz --out <dir>` (no flags) emits ~40 findings; the same command with `--no-reference` reproduces the expected zero-findings/pass result, matching plain `run_qc(bundled_default_config())`. Anyone reproducing a stage's "clean control fires nothing end-to-end" claim via the bare CLI (rather than `--no-reference` or the test harness) will see this and may mistake it for a regression; it is item 090's documented default behaviour operating on a fixture it was never calibrated against *(item 125, 2026-08-30)* → folded into CLAUDE.md Gotchas (a bare segfacet run defaults to the real-VerSe19 reference; corpus-fixture reproductions need --no-reference)

- [x] gap — **G3 acceptance not met, measured directly against the shipped pipeline.** Running every one of the 17 real VerSe19 subjects the decision document's scoliosis-selection rule (`coronal_deviation_mm >= 8.0` mm) selects through the shipped `run_qc` with `bundled_default_config()` (item 125, 2026-08-30): 1 of 17 fires a genuine `mislabel` offset finding — `sub-verse406_split-verse261`, label 17 (T10), `offset_mm = 18.51028119357566` against the shipped `max_offset_mm = 13.0` threshold. This is the same subject/level item 123 already identified as the single value that calibrated `13.0` mm in the first place (`insights.md`, item 123, 2026-08-29 entries), now confirmed to actually trip the rule end-to-end rather than merely sit near the threshold. Whether `18.51` mm is genuine coronal/kyphotic anatomy the envelope must accommodate or a GT labelling artefact (already flagged as worth inspecting directly, item 123) is unresolved; either way Stage 28's G3 acceptance box ("a real scoliotic curve in the VerSe cohort is not flagged as an offset outlier") stays unticked until it is *(item 125, 2026-08-30)* → roadmap.md Backlog — 'Adjudicate sub-verse406_split-verse261 T10…' (2026-08-30 triage), which records that Stage 28's G3 box stays open until the case is adjudicated

- [x] knowledge — The pipeline refits the identical in-sample centroid spline twice per case: `pipeline.py`'s curvature/tangent fit and `compute_leave_one_out_spline_offsets`'s internal reference refit at `features/spline_offset.py:444`; harmless but redundant, noted at the queue-017 pre-PR review *(items 119-123, 2026-08-30)* → roadmap.md Carried defects — 'The closest-point-on-spline search exists three times, and the pipeline refits the same spline twice per case' (2026-08-30 triage)

- [x] knowledge — three item-120/121/123 tests asserted byte/exact identity between a freshly-computed value and a **committed** artifact (`reference_default.json`, a golden's PCA `principal_axis`/`eigenvalue_ratio`) rather than going through the numeric-tolerance pattern item 078 established (`reports_close`; CLAUDE.md "Note what the golden tests actually assert") — the same defect class the convention exists to prevent, reintroduced in three separate items' own test-writing passes rather than in any src/ change. All three passed locally and on ubuntu-latest and were only caught by PR #56's CI matrix (numpy 1.26.4, numpy 2.0.2, windows-latest), where committed floats differ by ~1 ULP. Suggests the convention needs a lint or a shared fixture/helper name that makes "comparing against a committed artifact" reach for tolerance by construction, rather than relying on each item's test-writer to recall the rule *(items 120-123, 2026-08-30)* → roadmap.md Carried defects — 'Committed-artifact comparisons keep being re-authored byte-exact' (2026-08-30 triage), which proposes the shared helper + guard test and names the golden-retirement pull-forward

- [x] knowledge — a byte-compared generated artifact (item 103/124's `feature_catalogue.generated.{json,md}`) can stay flaky under 6g quantisation even after item 078's tolerance pattern is followed everywhere else: item 124's `observed.corpus` block embedded raw measurements from structurally-constant, sub-`NEGLIGIBLE_MAGNITUDE` paths (e.g. `magnitude=3.66317e-14`) whose exact bits are NumPy/SciPy cancellation-scale noise that differs across NumPy builds and CPU microarchitectures — `float(f"{v:.6g}")` cannot stabilise a value that is noise rather than signal, since noise quantised to six digits is still noise. PR #56's CI matrix failed the five byte-exact regeneration test modules (103/106/119/120/122; 8 tests) on one numpy-1.26.4 run and passed them on another with no code change. Fixed by clamping a covered-but-not-`informative` population's emitted numeric fields to `0.0` at the serialisation boundary only (`segfacet.observed_range.emission_range`, called from `catalogue.py`'s serialisers, never from `build_observed_ranges` itself) rather than by further quantisation. Any future byte-compared artifact that reports a raw float measurement alongside its own "is this value meaningfully nonzero" threshold should clamp sub-threshold noise to a fixed sentinel at emission, not merely round it *(item 124, 2026-08-30)* → roadmap.md Stage 29 D2 (tolerance by construction) carries the emission-clamp rule for artifacts that legitimately stay byte-compared (2026-08-30 triage)

- [ ] defect — `tests/test_116_ras_native_corpus.py`'s AC7 case-identity fence resolves its pre-migration reference by probing candidate refs for `tests/corpus/golden/clean_control.json` at the merge base (`_merge_base_sha`), and is marked `skipif(_MERGE_BASE_SHA is None)`. Item 126 retires those snapshots, so the probe keeps succeeding only while the merge base predates the retirement: once it reaches `main` and the base advances, all nine parametrised cases silently degrade to a skip rather than failing. The fence is not broken by the deletion itself (it reads git history, not the working tree) and item 126 leaves it untouched; making it durable needs a decision — pin the last pre-retirement commit as a constant, or delete the fence as discharged *(item 126, 2026-08-30)*

- [ ] knowledge — `docs/aide/golden-decision-table.md`'s `tests/golden/022_stage3_report.json` row describes the consuming test's write-and-skip behaviour as "a logged, unfixed defect", but item 111 fixed it (`tests/test_111_golden_guard.py::test_ac5_no_self_healing_branch_in_test_ac8` now forbids both `pytest.skip` and a write inside that function). The cell is signed maintainer text and cannot be corrected in place, so the stale clause survives verbatim; item 126 records the correction in the table's retirement execution log instead *(item 126, 2026-08-30)*

- [ ] knowledge — after item 126 retires the eleven snapshot goldens, two process-owned documents name paths that no longer exist and cannot be corrected from inside a work item: `CLAUDE.md`'s "Note what the golden tests actually assert" paragraph (which explains `reports_close` against the committed corpus goldens) and `.aide/conventions.md`'s `tests/corpus/golden` mention. Both are PR-gated framework/process files and need a reviewed PR rather than an item edit *(item 126, 2026-08-30)*

- [ ] gap — `golden-decision-table.md`'s `asserted by` column is hand-maintained and has gone stale in the one direction nothing checks: `tests/test_105_golden_decision_table.py`'s AC6 verifies every named test *exists*, but nothing verifies that every test actually consuming a fixture is *named*. Measured 2026-08-30, an AST sweep of `tests/` for `GOLDEN_DIR`/`load_golden`/`read_golden_text`/`check_case_golden` found twelve consuming modules against the six the table lists — items 106, 108, 116, 119, 120, 121, 122 and 123 each added a consumer without a table edit, so the golden retirement's blast radius was three times the queue's estimate. A completeness check in the other direction (or generating the column) would have surfaced this at authoring time rather than at execution time *(item 126, 2026-08-30)*
