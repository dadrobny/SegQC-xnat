# FACET — Work Queue 016

> **Created:** 2026-08-12
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 26**; supersedes the completed [`queue-015.md`](queue-015.md)
> (Stage 19, closed 2026-08-11).

---

## Scope of this queue

Delivers roadmap **Stage 26 — Carried-Defect Remediation (pre-real-data)**
(G2, G7) in full: eight diagnosed defects that Stages 17–19 recorded but were
correctly forbidden from fixing in scope, plus the stage validation. Every
item has a named location and a known cause — **this stage does no
discovery**, and an item that turns into an investigation should hand back
rather than widen.

**Why this stage runs before Stage 20.** Stage 20 audits rule↔mode↔feature
traceability and adopts a specificity ratchet. Items 108 (face-mapping
semantics), 109 (per-mode attribution) and 110 (an unreachable feature module)
all change the surfaces that audit measures, so auditing first would record
findings that are about to move. Item 108 is additionally a prerequisite for
any real-data claim (Stages 16/21): every `border`/`fov` finding on data read
through `segfacet.io` currently names the wrong anatomical face.

**Why this queue is scoped to exactly one stage.** Stage 26 comes to nine
items — eight defects plus the stage validation, with D6 and D7 combined into
one documentation-corrections item — under `loop.queue_cap = 10`. Stage 20
depends on this stage's fixes and is its own audit with a different shape of
work, so it stays out of this batch per the stage-boundary convention.

### The first item changes what the rest of this queue costs

Five shipped items (099, 100, 101, 103, 105) pin SHA-256 digests of committed
source as "untouched" scope fences, and item 106 extends the pattern to
individual `progress.md` rows. **Every item in this queue that edits
`src/segfacet/**` breaks one or more of them by design** — item 114's
comment-only edit trips three `heuristics/**` digests plus
`_PRE_105_SRC_HASH`. Item 107 retires that instrument and lands its
replacement, so the rest of the queue can edit source without a re-pin toll.

**If item 107 is deferred or slips**, the following protocol applies to every
item that runs before it: re-pin the affected constant *in the same commit*,
with a comment naming that item's authorisation — the `_PRE_100_HASHES`
precedent, and item 106's re-pin of `_PRE_105_SRC_HASH`. A re-pin is not scope
creep; failing to re-pin leaves the suite red.

| Constant | Location | Covers |
|---|---|---|
| `_PRE_099_HASHES`, `_PRE_099_HEURISTICS_COMBINED_HASH`, `_PRE_099_GOLDEN_COMBINED_HASH` | `tests/test_099_per_mode_metrics.py` | `report_schema_v0.json`, `cli.py`, `eval/metrics.py`; `heuristics/**`; `tests/corpus/golden/**` |
| `_PRE_100_HASHES`, `_PRE_100_{SYNTH,HEURISTICS,FEATURES,CORPUS}_HASH` | `tests/test_100_severity_ladder.py` | + `eval/per_mode.py`, `eval/eval_report_schema_v0.json`; `synth/**`, `features/**`, `tests/corpus/**` |
| `_PRE_101_HASHES`, `_PRE_101_{HEURISTICS,FEATURES,SYNTH,CORPUS}_HASH` | `tests/test_101_per_mode_cohort.py` | + `eval/{overlap,severity_ladder,calibrate}.py` |
| `_PRE_103_HASHES`, `_PRE_103_{FEATURES,HEURISTICS,EVAL,SYNTH,REFERENCE,CORPUS}_HASH` | `tests/test_103_feature_catalogue.py` | + `reference/**` |
| `_PRE_105_SRC_HASH`, `_PRE_105_CORPUS_HASH` | `tests/test_105_golden_decision_table.py` | the **whole** `src/segfacet/**` tree and `tests/corpus/**` |
| `_PRE_106_OBJECTIVE_ROW_DIGESTS`, `_PRE_106_OUTCOME_TARGETS_DIGEST`, `_PRE_106_REAL_CORPUS_ROW_DIGEST` | `tests/test_106_stage19_validation.py` | named rows of `docs/aide/progress.md` |

Which item would trip what, absent item 107: **108** → features + heuristics +
src tree (+ corpus and golden hashes if regenerated goldens change any
`touches_*` value); **109** → src tree only; **110** → features + src tree +
corpus/golden; **112** → the named `eval/per_mode.py` digest in *both* the 100
and 101 sets, plus src tree; **114** → the three `heuristics/**` digests + src
tree, for a comment-only edit. **111** and **113** touch no source and trip
nothing.

Two committed artifacts are regenerated, never hand-edited, whenever the
realised record shape changes (item 110):
`docs/aide/feature_catalogue.generated.json` and `.md`, via
`python -m segfacet.catalogue`.

**Prioritisation.** Item 107 first — it removes the re-pin burden from four
later items and replaces a control that has produced six documented failures
and no recorded true positive, so every hour it is deferred is paid twice.
Item 108 next: it is the correctness blocker for real data and has the widest
blast radius, so later items rebase onto its regenerated goldens rather than
the reverse. 109 is independent (`eval/` only) and may run in parallel. 110 is
sequenced adjacent to 108 so the two items that regenerate corpus goldens are
neighbours and the corpus is regenerated once per cause. 111–114 are cheap,
mutually independent hygiene and may run in any order. 115 closes the stage and
must run last. Recommended order: **107 → 108 → 109 → 110 → 111 → 112 → 113 →
114 → 115**.

**Where a human steer is worth having.** Item 110 is a genuine fork (wire the
module in, or delete it and reword a shipped Stage 3 claim) and item 114
carries a maintainer's call on how to resolve a ticked-but-unmet acceptance
box. `aide.toml` sets `clarify = "assume"`, so under unattended execution a
spec author will pick and record a default. Running this queue through
`/aide-spec-queue 016` front-loads both decisions into one interactive sitting.

**Numbering.** Continues at the next free integer: **107–115**, plus **116**, inserted 2026-08-12 during execution (see below).

### Stage-26 deliverable → item coverage

| Stage-26 deliverable | Delivered by item |
|---|---|
| **D9** Byte-hash scope fences retired; diff-based scope check landed in their place | 107 |
| **D2** RAS-correct `touches_*` face mapping and its consuming rules | 108 |
| **D1** `normalised_delta` magnitude-sensitive attribution | 109 |
| **D8** `features/neighbourhood.py` wired or retired | 110 |
| **D3** Golden-fixture test hygiene (`.gitattributes` pin, self-healing golden) | 111 |
| **D4** `compute_per_mode_metrics(overlap_result=…)` short-circuit | 112 |
| **D5** `test-numpy-majors` scoped off environment-gated modules | 113 |
| **D6** + **D7** Documentation corrections (`bounds.py` comments, Stage 17 acceptance box) | 114 |
| **D10** Synthetic corpus migrated RAS-native, completing the axis-convention change | 116 |
| Stage validation + verification-row closure | 115 |

---

## Work items

### Item 107: Retire the byte-hash scope fences, land a diff-based scope check

Delete the `_PRE_NNN_*` byte-hash scope fences from
`tests/test_{099,100,101,103,105}_*.py` and the `progress.md` row digests from
`tests/test_106_stage19_validation.py`, and land the deterministic check they
were reaching for in their place. **Do not delete without replacing** — the
motivation behind the fences is sound (a machine check behind the validator's
prose "code stays within scope" gate), only the instrument is wrong. A fence
encodes a **diff-time** property (*"item N did not modify file X"*) as a
**permanent runtime invariant** (*"file X equals these bytes forever"*), which
is a different and false claim the moment a later item is legitimately
authorised to edit X — the normal case, not the exception. Item 104's own
Decisions log already reached this verdict and made its equivalent ACs
"git-diff obligations on the validator, not pytests"; items 104 and 106 use
that pattern, 099–101/103/105 are legacy from before the call. The record: six
documented failures (three Windows-CI-only and invisible to every local gate,
one where the pinned digest was never reproducible even on an unchanged tree
because `rglob("*")` swept `__pycache__`, two sibling-collisions with a later
item's authorised edit) and **no recorded true positive** anywhere in
`docs/aide/items/` or `insights.md`. Replacement: a small
`scripts/check_item_scope.py` that reads an `## Authorised paths` glob list
from a work-item spec, computes `git diff --name-only $(git merge-base main
HEAD)`, and exits non-zero naming any changed path outside the list — plus the
spec-section convention itself, so items 108-115 declare their authorised
paths and the validator runs the check as a spec obligation. **The check
belongs to the branch, never to pytest**: a diff-scope assertion has nothing
to assert once merged to main, and forgetting that is precisely what produced
the fences. Preserve what is not a fence and must survive: intra-run
determinism assertions (`dest1 == dest2`), item 104's drift test (a live
relation between two things that both move, which self-heals on legitimate
change), and item 098's expected-value baselines (behaviour, not bytes).
*Testable:* the full suite is green with every fence removed; the script exits
non-zero, naming the path, when run against a branch that touches a file
outside its spec's `## Authorised paths`, and zero when it does not; a spec
with no `## Authorised paths` section is a hard error, not a silent pass; the
script requires no network, no venv beyond stdlib, and completes in under a
second on this repo.

### Item 108: RAS-correct `touches_*` face mapping

Correct the anatomical face naming in
`src/segfacet/features/geometry.py` (lines ~251-256) and audit every consumer.
Since item 094 every volume loaded through `segfacet.io` is reoriented to
`("R", "A", "S")` (`io.py:166`), so array axis 0 runs left→right, axis 1
posterior→anterior and axis 2 inferior→superior — while the extractor still
maps `x == 0 → touches_inferior`, `y == 0 → touches_left`,
`z == 0 → touches_anterior`, a convention the module's own docstring describes
as "pragmatic … for tools that work in any orientation without a reliable RAS
header". That premise no longer holds: the header *is* reliable and the layout
*is* normalised, so the six flags are systematically mis-named and every
`border` / `fov` finding on real data names the wrong face. Re-map the flags to
true RAS anatomy, update the docstring to state the RAS precondition rather
than the old any-orientation caveat, and audit `heuristics/border.py` and
`heuristics/fov.py` (item 089) for any assumption that the "inferior/superior"
pair is the long axis of the spine. Decide and record whether in-memory arrays
built by `tests/synthetic.py` / `synth/clean_gt.py` (spine along axis 0, never
round-tripped through `io`) are brought into the same convention or explicitly
documented as a rung-1 exception — the two must not silently disagree.
Regenerate any committed golden whose `touches_*` values change. *Testable:* a
fixture whose spine runs along the RAS superior axis reports `touches_superior`
/ `touches_inferior` on the cranio-caudal faces and `touches_left` /
`touches_right` on the left-right faces; a volume stored in a non-RAS
orientation produces the same flags after loading as its RAS-native
equivalent; `border` / `fov` findings on a case cropped at a known anatomical
face name that face; a regression test pinning the pre-fix (wrong) mapping is
shown to fail before the change.

### Item 109: Magnitude-sensitive per-mode attribution

Repair `normalised_delta` in `src/segfacet/eval/per_mode_cohort.py`, whose
`delta / max(|value_a − baseline|, |value_b − baseline|)` scale saturates to
exactly ±1.0 whenever either run sits on its metric's baseline. Because 7 of
the 8 `PER_MODE_METRIC_SPECS` baselines are `0.0`, any comparison in which two
or more modes return to baseline ties at 1.0 across all of them, and
`attributed_mode` is then decided by the documented lowest-mode tie-break
rather than by which mode actually moved further — so Stage 18's run-vs-run
**attribution** deliverable does not do what its own docstring claims. Two
existing tests demonstrate the trap on deliberately different-magnitude inputs
(item 101's `test_ac13_*` and `test_ac16_*`). Choose and record a scale that
stays magnitude-sensitive when a run sits on baseline — a fixed per-mode
reference excursion, the observed cohort range, or an explicit
`normalised_delta is None` for the degenerate case are all candidates — keep
the tie-break as the last resort it was meant to be, and update the affected
tests plus `eval/report.py`'s rendering. *Testable:* a fixture where mode A
moves 0.1 and mode B moves 0.9 from a shared `0.0` baseline attributes to B,
not to the lower mode number; the existing `compare_runs` outputs are unchanged
wherever neither run sits on baseline; the degenerate all-zero case still
resolves deterministically and is documented.

### Item 110: `features/neighbourhood.py` — wire it in, or retire it

Resolve the dead wiring behind Stage 3's ✅ claim that local vertebra
neighbourhood comparison "flags isolated anatomical outliers".
`src/segfacet/features/neighbourhood.py` implements the sliding-window (±N)
deviation score in full and has its own test module
(`tests/test_024_neighbourhood_comparison.py`), but it is imported by
**nothing**: absent from `pipeline.py::extract_feature_record`, from
`feature_report.py`'s block assembly and from all 10 registered rules, which
is why it never appeared in item 103's 111-entry catalogue. No case's report or
verdict has ever been influenced by it. Pick one branch and record why:
**wire it** — add it to the realised record, decide whether it needs a
consuming rule or lands as an `unwired` feature (legitimate under Stage 20's
traceability semantics), and reconcile its mean/std deviation score with the
percentile-based `robust_z` / `percentile_rank` / `out_of_range` machinery
item 106's Group 11 retune already flags; or **retire it** — delete the module
and its tests and reword Stage 3's deliverable and acceptance bullets to match
what shipped. Wiring changes the record shape, so regenerate
`docs/aide/feature_catalogue.generated.{json,md}` via `python -m
segfacet.catalogue` and expect item 104's drift test and item 105's AC7 live
`N/67` recount to move. *Testable:* whichever branch is taken, no `*(Item
024)*` claim in `progress.md` survives that is not backed by observable
pipeline behaviour; if wired, the new leaf paths appear exactly once in the
regenerated catalogue and item 104's drift test passes in both directions; if
retired, no import of the module remains anywhere in `src/` or `tests/`.

### Item 111: Golden-fixture test hygiene

Close two independent defects in how committed goldens are guarded, both found
during item 105's survey and both out of scope there. **(a)** `tests/golden/*.json`
(`016_features_report.json`, `022_stage3_report.json`) are the only committed
byte-reproducible text fixtures absent from `.gitattributes`; every other family
is pinned `text eol=lf`. It is latent only because both consumers compare with
`read_text()`, whose universal-newline translation hides a CRLF checkout — the
moment any future item switches either comparison to `read_bytes()` it
reproduces the Windows-CI-only failure documented three times over for items
099-101. **(b)** `tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot`
writes its own golden and `pytest.skip`s when the file is absent (lines
~786-789), so **deleting the golden makes the check pass** — the opposite of
`synth/golden.py::read_golden_text`, whose docstring states that "a missing
golden must fail loudly, never silently pass", and of
`test_042_golden_determinism.py::test_ac14_missing_golden_fails_loudly`. The
sibling `test_016_features_json.py::test_ac5_golden_snapshot` has no such
branch and is the model. Note both goldens carry a **retire** disposition in
`docs/aide/golden-decision-table.md`, so record whether this item fixes them or
retires them early; do not silently do both. *Testable:* `.gitattributes` pins
`tests/golden/*.json text eol=lf` and the committed blobs are verified
`\r`-free; deleting `tests/golden/022_stage3_report.json` makes its test
**fail**, not skip; `git check-attr` reports the pin for both files.

### Item 112: `compute_per_mode_metrics(overlap_result=…)` short-circuit

Add an optional `overlap_result=None` keyword to
`src/segfacet/eval/per_mode.py::compute_per_mode_metrics` that skips the
internal `compute_overlap` call when a caller already holds the result, and
pass it from `eval/harness.py::evaluate_case`, which computes exactly that
`OverlapResult` for its own `overlap` field (`harness.py:407`) immediately
before item 101's `per_mode=True` hook recomputes it over the same three
inputs. Item 101 accepted the duplicate pass rather than widen an API that
items 099/100 had frozen; this item is where that is legitimately open. Purely
additive — the default path and every existing call site must behave
identically. *Testable:* results are identical with and without the keyword on
the same inputs; a spy/counter confirms `compute_overlap` is called once per
case through the harness where it was previously called twice; passing a
mismatched `overlap_result` is either rejected or documented as caller-trusted,
and the choice is tested.

### Item 113: Scope `test-numpy-majors` off environment-gated modules

Restrict the `test-numpy-majors` CI job (`.github/workflows/ci.yml`, added by
item 095) so it no longer runs the Docker- and PyRadiomics-gated modules. The
job exists to prove numpy-major agnosticism, but it runs the **full** suite per
numpy leg, and on GitHub's `ubuntu-latest` runners — which have a real Docker
daemon, unlike many local dev venvs — the Docker-gated smoke tests
(`test_066_dockerfile.py`, `test_069_container_smoke.py`,
`test_070_acceptance_stage9.py`) attempt a real `docker build` and have failed
on Docker Hub anonymous-pull rate-limiting rather than on any numpy
incompatibility. That is incidental flakiness with no verification value, now
doubled (once per numpy leg, on every push), while the dedicated
`verify-environment-gated` job already owns real Docker verification. Use
`--ignore` / a marker-based deselection, whichever leaves the intent legible in
the workflow file, and state in a comment what the job does and does not cover.
*Testable:* the job's collected test set excludes the three Docker modules and
the PyRadiomics-gated tests, and still includes every numpy-sensitive module;
`verify-environment-gated`'s coverage is unchanged; a local dry run of the same
selection expression collects the expected counts.

### Item 114: Documentation corrections — `bounds.py` comments and Stage 17's acceptance box

Two small, unrelated documentation defects, batched because neither justifies
its own execution cycle. **(a)** `src/segfacet/heuristics/bounds.py` (comments
near lines ~44, ~53, ~59) still reads "S and Cocygis are intentionally omitted
(unbounded)" — labels item 093 retired when the TPTBox convention became the
default. The *behaviour* is correct and must not change (`_LEVEL_GROUP` derives
the omission generically from `CANONICAL_ORDER` by name prefix, so `S1`-`S6` /
`Cocc` are still correctly unbounded); only the comment text names labels that
no longer exist. **(b)** `progress.md`'s Stage 17 acceptance list renders its
fourth box as `- [x] A real segmenter output round-trips with correct level
names.` while that line's own annotation opens *"Not ticked: no real SPINEPS
output is available…"* — the checkbox and the prose give opposite answers. Item
097's Decisions log makes the intent clear (unmet in reality, met in
mechanics), and the honest state is already carried by the Environment-Gated
Capability Verification row "Real SPINEPS-output label-convention round-trip ❓
Unverified". Resolve the contradiction — untick, reword, or adopt a third state
— and check whether anything in `aide check`'s rollup pressures a ✅ stage into
ticking every box, because if it does, that pressure is itself the defect worth
recording. *Testable:* no comment in `heuristics/bounds.py` names a label
absent from `CANONICAL_ORDER`, and the rule's behaviour is byte-identical on
the corpus; `progress.md`'s Stage 17 acceptance box and its annotation agree
with each other and with the verification row; `aide check` reports no new
warning.

### Item 116: Make the synthetic corpus RAS-native

**Inserted 2026-08-12, mid-execution.** Item 108 revealed that `synth/` is not
merely inconsistent with the affine — it implements a *documented* array-axis
convention (`clean_gt.py`: *"Axis convention (matching
`segfacet.features.geometry`): image axis 0 is superior-inferior … Bodies are
stacked along axis 0"*) that item 108's affine-derived mapping replaces. 14 tests
across six pre-existing modules fail on item 108's branch as a result. This item
completes the migration: bodies stack along **axis 2**, the plain diagonal affine
becomes truthful, loading is an array-identity operation, and every operator that
names a face resolves its axis through the affine. Fixtures, manifest and goldens
are regenerated; the tests encoding the legacy convention are updated to assert
anatomical intent rather than a hardcoded face. Case identity is preserved — a
case designed to trip `border` still trips `border` on the same labels — while
numeric feature values legitimately move. **Branches off
`aide/108-ras-correct-touches-face-mapping`** and merges into `aide/queue-016`
with it: migrating fixtures under the pre-108 mapping would break the same tests
in mirror image and name cranio-caudal faces "anterior" for one item's duration.
*Testable:* the affine-derived S/I axis matches the axis body centroids vary
along; loading a fixture leaves the array unchanged; cropping toward each of the
six faces sets that face's flag; every corpus case trips the same
`(rule_id, labels)` as before; `crop_at_border` sensitivity is restored in the
Stage-7/14 acceptance suites; fixtures, manifest and goldens regenerate
byte-identically twice over; `tests/test_108_affine_faces.py` passes unchanged.

### Item 115: Validate stage 26: Carried-Defect Remediation

Replay Stage 26's use cases end-to-end rather than re-running the unit suite.
Confirm each of the eight defects has a regression test that demonstrably fails
against the pre-fix behaviour — for the three where that is cheap to stage
live (108's face mapping, 109's attribution, 111's missing golden), revert the
fix in a scratch tree, observe the red, and restore. Run a full case through
`segfacet run` on a fixture cropped at a known anatomical face and confirm the
emitted `border` / `fov` findings name that face correctly (**G2**); run a
run-vs-run per-mode comparison on two runs constructed with a large move in one
mode and a small move in another, and confirm the attribution follows magnitude
(**G7**); confirm the `neighbourhood.py` fork from item 110 is fully executed
on both sides — reachable *and* catalogued, or absent *and* de-claimed in
`progress.md` with no orphaned import or test. Confirm item 107's replacement
check is real: no `_PRE_NNN_*` fence remains in `tests/`, every item in this
queue declared `## Authorised paths`, and `scripts/check_item_scope.py`
correctly flags a deliberately out-of-scope edit on a scratch branch. Confirm
the full suite is green on a **fresh clone in a different directory** (the
item-099 sandbox-path class of bug is invisible otherwise). Then update
`progress.md`: tick Stage 26's five acceptance criteria against what was
actually exercised, flip any Environment-Gated Capability Verification row this
stage affects to ✅ Verified where the environment allows (`python
.aide/scripts/aide.py env --profile <name>`), otherwise record why it stays ❓
Unverified, and confirm no Stage 3 or Stage 17 claim remains that observable
behaviour does not back. *Testable:* each acceptance criterion is ticked with a
recorded evidence sentence naming what was run; the fresh-clone suite is green;
the fence-retirement audit is recorded; `aide check` reports no new warnings.

---

## Current state (2026-08-12)

Generated on completion of [`queue-015.md`](queue-015.md), which delivered
**Stage 19 — Generated Feature & Rule Catalogue + Steering Review** (items
103–106, all ✅). Opens **Stage 26 — Carried-Defect Remediation**, scoped
2026-08-11 from triaged [`insights.md`](../insights.md) entries and sequenced
ahead of Stage 20 because its fixes change the surfaces that audit measures.
Stage 20 (traceability matrix + specificity ratchet) is next after this queue;
Stage 27 (feature schema taxonomy) follows Stage 20; Stages 16 and 21 remain
blocked behind that chain. Stage 11 stays ⏸️ Deferred and Stage 15 ❌ Excluded.
