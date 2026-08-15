# Item 115 — Validate stage 26: Carried-Defect Remediation

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 115
> **Objectives:** G2, G7
> **Suggested branch:** `aide/115-validate-stage26`

---

## Description

Close Stage 26 by **replaying its use cases end-to-end**, not by re-running the
unit suite. Stage 26 exists because eight diagnosed defects had accumulated
without owners — a ninth, item 116, was found during execution and inserted;
the stage's claim is that they are fixed, so this item's job is
to demonstrate each fix against the behaviour it replaced, then record what was
actually exercised in `progress.md`.

Two validation obligations are specific to this stage. First, **red-then-green
evidence**: a remediation stage whose regression tests were written after the
fix proves nothing, so the three cheapest-to-stage defects are re-broken in a
scratch tree and observed failing. Second, a **fresh-clone run in a different
directory** — item 099's absolute-path bug passed every local gate, a from-scratch
`git clone` in another directory, and both validator rounds, and was caught only
by reading the Actions tab; a checkout at a different path is the cheapest
approximation of that.

**In scope.** Replay, evidence recording, `progress.md` acceptance ticks, and
Environment-Gated Capability Verification row updates.

**Not in scope.** Fixing anything found. A genuine defect surfaced here is
logged to `insights.md` and, if it blocks a stage claim, the stage stays open
and this item reports that rather than ticking around it.

## Acceptance Criteria

- [ ] **AC1: every defect has a demonstrably-failing regression test.** For each
  of items 107-114 and 116, the test that pins its fix is identified by name, and its
  relationship to the pre-fix behaviour is recorded.
- [ ] **AC2: red-then-green is observed for item 108.** The affine-driven face
  mapping is reverted in a scratch tree, the face test observed failing, and the
  tree restored.
- [ ] **AC3: red-then-green is observed for item 109.** The attribution scale is
  reverted, the differential-magnitude test observed failing, and restored.
- [ ] **AC4: red-then-green is observed for item 111.** `tests/golden/022_stage3_report.json`
  is deleted in a scratch tree, the snapshot test observed **failing** (not
  skipping), and restored.
- [ ] **AC5: `border`/`fov` name the right face end-to-end (G2).** A full
  `segfacet run` on a fixture cropped at a known anatomical face emits a finding
  naming that face; the report excerpt is recorded.
- [ ] **AC6: attribution follows magnitude end-to-end (G7).** A run-vs-run
  comparison over two runs built with a large move in one mode and a small move
  in another attributes the large one; reversing the magnitudes reverses the
  attribution. Both outputs recorded.
- [ ] **AC7: the neighbourhood fork is fully executed.** Item 110's outcome is
  verified on both sides: the module is reachable from `extract_feature_record`
  **and** present in the regenerated catalogue with `status: "unwired"`, and no
  `progress.md` claim about it remains that observable behaviour does not back.
- [ ] **AC8: no byte-hash fence remains — searched by assertion shape, not by
  name.** A fence is *a SHA-256 taken over a committed file's bytes and compared
  against a hardcoded literal*. Searching for the `_PRE_[0-9]` naming pattern is
  **not sufficient** and must not be the check: item 107's own AC1 did exactly
  that and missed three survivors, one of which
  (`_PRE_ITEM_REFERENCE_DEFAULT_SHA256` in
  `tests/test_093_tptbox_label_convention.py`) then fired on item 116's
  legitimate regeneration of `reference_default.json`. One is known to remain at
  the time of writing — `tests/test_098_stray_components.py`'s pinned pre-098
  digest of `reference_verse_v1.json` (`_PRE_098_REFERENCE_VERSE_V1_SHA256`,
  `test_ac18_reference_verse_v1_bytes_unchanged`) — and this item must either
  retire it or record why it stays.
  **Correction (item 115, 2026-08-15):** this AC as originally drafted also
  named `tests/test_102_stage18_validation.py`'s "path-to-digest dict asserted
  around line 668" as a second known-remaining fence. It is not one, and the
  line number was wrong besides: the real comparison is
  `test_adv_no_mutation_of_manifests_and_fixtures` (lines ~692-719), whose
  `before` dict is built from `hashlib.sha256(...)` calls **in the same test
  run**, then the fixtures are re-hashed and compared against that same
  in-run dict — an intra-run no-mutation assertion, exactly the shape this
  AC's own discriminator (below) says must survive untouched, not a fence.
  **The discriminator:** a digest compared against a *hardcoded constant* is a
  fence; a digest compared against a value *computed in the same run* (hash,
  run the code, re-hash, compare) is an intra-run determinism assertion and must
  survive untouched.
- [ ] **AC9: every queue-016 item declared `## Authorised paths`.** All ten
  specs carry the section (item 116 was inserted mid-execution), and item 107's checker parses each without error.
- [ ] **AC10: the checker catches a real violation.** On a scratch branch, an
  edit outside an item's authorised paths makes
  `scripts/check_item_scope.py` exit non-zero naming that path; the output is
  recorded.
- [ ] **AC11: the fresh-clone suite is green.** The full suite passes from a
  clean `git clone` into a directory whose path differs from this checkout's,
  in a fresh venv. The clone path is recorded.
- [ ] **AC12: Stage 26's acceptance is ticked honestly.** All five acceptance
  criteria in `progress.md`'s Stage 26 section are ticked with a one-sentence
  evidence note naming what was run — or left unticked with the reason.
- [ ] **AC13: verification rows reflect reality.** Any Environment-Gated
  Capability Verification row this stage affects is flipped to ✅ Verified where
  `python .aide/scripts/aide.py env --profile <name>` allows, and otherwise
  records why it stays ❓ Unverified. Item 113 must not have flipped the Docker
  row by reducing where Docker runs.
- [ ] **AC14: `aide check` reports no new warning.**
- [ ] **AC15: findings are logged, not silently fixed.** Anything discovered
  during replay that is not a Stage 26 deliverable is appended to
  `insights.md` and named in this item's Decisions.

## Assumptions

- **Items 107-114 and 116 are all ✅ before this item starts.** If any is incomplete,
  this item halts and reports rather than validating a partial stage — the same
  posture item 106 took on a pending sign-off.
- **Red-then-green is staged in a scratch tree, never on the branch.** Reverts
  are made, observed and discarded; no revert is committed.
- **Three defects are enough for AC2-AC4.** Items 107, 110, 112, 113, 114 and 116 are
  verified by inspection and their own tests rather than by re-breaking, because
  re-breaking them means deleting a script, unwiring a module, or editing CI —
  disproportionate to the evidence gained. The choice is recorded.
- **A "different directory" clone is the available proxy for a different
  platform.** It catches the absolute-path class of bug, not the line-ending or
  path-separator classes; those remain CI's job, and this item records that
  limit rather than implying broader coverage.

## Implementation Steps

1. Confirm items 107-114 and 116 are ✅ in `progress.md`; halt if not.
2. For each item, identify the pinning test by name and record it (AC1).
3. Stage AC2/AC3/AC4's reverts one at a time in a scratch tree, observe the
   failure output, restore, and record each.
4. Run the AC5 and AC6 end-to-end replays; capture the report excerpts.
5. Verify AC7 against the regenerated catalogue and `progress.md`.
6. Search `tests/` for the fence *shape* — a `hashlib.sha256(...)` over a
   committed file compared against a hardcoded literal — not for the
   `_PRE_[0-9]` name (AC8); parse every queue-016 spec with the checker (AC9);
   stage the AC10 violation on a scratch branch.
7. Clone into a fresh directory, build a venv, run the full suite (AC11).
8. Update `progress.md`: Stage 26 acceptance ticks with evidence, verification
   rows, and the deliverable statuses.
9. Run `aide check` (AC14); log anything found to `insights.md` (AC15).

## Testing Strategy

New module `tests/test_115_stage26_validation.py` for the assertions that can be
made in-suite; the replays themselves belong to the Validation section:

- AC8: assert no digest-vs-hardcoded-literal comparison over a committed file
  remains under `tests/`, and that the intra-run before/after digests still do.
- AC9: assert each of the ten specs has a non-empty `## Authorised paths`.
- AC7: assert the neighbourhood paths are in the committed catalogue with
  `status: "unwired"`, and that `progress.md`'s item 024 bullets match.
- AC12: assert every Stage 26 acceptance box is either ticked **and** followed
  by an evidence annotation, or unticked **and** followed by a reason — the
  tick-implies-evidence biconditional item 106 established.
- AC13: assert the Docker verification row is unchanged in state by item 113.

Adversarial: a spec with an `## Authorised paths` heading but no bullets; a
Stage 26 box ticked with no annotation (must fail); a `_PRE_` constant
reintroduced in a comment (decide and document whether that counts).

## Validation

This item **is** the validation. Record, in Decisions: each red-then-green
observation with its failure output; the AC5 and AC6 report excerpts; the AC10
checker output; the AC11 clone path, venv creation and suite result; and the
`aide check` output. A replay that could not be performed is recorded as such,
never inferred from a green suite.

## Dependencies

Items 107, 108, 109, 110, 111, 112, 113, 114 — all must be ✅; this item
validates their combined result and closes the stage.

## Authorised paths

- `tests/test_115_stage26_validation.py`
- `docs/aide/progress.md`
- `docs/aide/insights.md`
- `docs/aide/items/115-validate-stage26.md`

## Decisions & Trade-offs

### AC1 — pinning test per defect

| Item | Defect | Pinning test | Relationship to pre-fix behaviour |
| --- | --- | --- | --- |
| 107 | `_PRE_NNN_*` byte-hash scope fences | `tests/test_107_item_scope_check.py::test_ac1_no_pre_099_100_101_103_105_fence_constant_remains_under_tests` | Absence assertion: pre-fix, these five items' fence constants existed and repeatedly false-fired (six documented failures, `insights.md`); the test pins that none remain and self-heals if a future item legitimately needs one again. |
| 108 | `x == 0 -> touches_inferior` etc. hardcoded axis mapping | `tests/test_108_affine_faces.py::test_ac2_ras_face_named_correctly` (plus `test_ac1_no_hardcoded_axis_literal_assignment`) | Reverting `compute_label_geometry` to the pre-fix hardcoded assignment reproduces the exact mis-naming for all six parametrised RAS faces — observed live, see AC2 below. |
| 109 | `normalised_delta` saturates to ±1.0 on a baseline run | `tests/test_109_attribution_scale.py::test_ac7_point_one_vs_point_nine_from_shared_baseline_attributes_to_the_larger_move` | Reverting `compare_runs`'s scale to the old adaptive `max(abs(value_a-baseline), abs(value_b-baseline))` formula reproduces the saturation exactly (`1.0` instead of `0.1`) — observed live, see AC3 below. |
| 110 | `neighbourhood.py` dead wiring | `tests/test_115_stage26_validation.py::test_ac7_neighbourhood_reachable_from_extract_feature_record` / `test_ac7_catalogue_lists_neighbourhood_entries_as_unwired` (item 110's own `tests/test_110_neighbourhood_wiring.py` pins the generalised API) | Verified by inspection, not re-broken (Assumptions): pre-fix the module was implemented and importable but absent from `extract_feature_record`/the catalogue/every rule — item 110's tests assert the wiring now exists. |
| 111 | `test_ac8_golden_snapshot` self-heals (skips) on a missing golden | `tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot`, pinned by `tests/test_111_golden_guard.py::test_ac5_no_self_healing_branch_in_test_ac8` | Deleting `tests/golden/022_stage3_report.json` pre-fix made the test **pass** (self-healing skip); post-fix it **fails loudly** — observed live, see AC4 below. |
| 112 | `compute_per_mode_metrics` always recomputes overlap | `tests/test_112_overlap_short_circuit.py::test_ac3_no_internal_compute_overlap_call_when_result_supplied` | Verified by inspection: pre-fix there was no `overlap_result=` parameter at all, so every caller paid a second full overlap pass; the test monkeypatches `compute_overlap` and asserts it is *not* called when a result is supplied. |
| 113 | `test-numpy-majors` runs Docker/PyRadiomics-gated modules | `tests/test_113_ci_numpy_matrix_scope.py::test_ac7_scoped_collection_removes_exactly_the_gated_node_ids` | Verified by inspection: pre-fix the job ran the full `python -m pytest` per numpy leg, exposing it to Docker-registry flakiness with no verification value; the test does a real `--collect-only` diff proving the gated node ids are now excluded. |
| 114 | stale `S`/`Cocygis` comments in `bounds.py`; Stage 17 box/annotation contradiction | `tests/test_114_documentation_corrections.py::test_ac1_no_retired_label_name_in_bounds_py_source` and `::test_ac4_fourth_acceptance_box_is_unticked` | Verified by inspection: pre-fix `bounds.py` named retired labels in comments (behaviour unaffected), and `progress.md:744` was ticked while its own annotation said "not ticked" — both regression-pinned now. |
| 116 | synthetic corpus stacked bodies along array axis 0, not affine-truthful | `tests/test_116_ras_native_corpus.py::test_ac1_bodies_stack_along_array_axis_2` (plus `test_ac2_affine_truthful_for_every_generated_fixture`, `test_ac8_mode6_crop_at_border_sensitivity_is_restored_to_one`) | Verified by inspection, not re-broken (Assumptions): pre-fix the corpus's array-axis-0 convention contradicted item 108's affine-derived face mapping; item 116 migrated the corpus RAS-native and regenerated fixtures/manifest/goldens. |

Items 107, 110, 112, 113, 114, 116 are verified by inspection of their own
committed tests rather than by re-breaking, restating the Assumptions'
choice: re-breaking any of them means deleting a script (107, 113), unwiring
a module (110), editing CI (113), or reverting a whole-corpus migration
(116) — disproportionate to the evidence gained relative to reading their
own committed, already-passing regression tests. 112's fix is a pure
additive keyword-argument short-circuit with no removable "old behaviour" to
revert to (there was no `overlap_result=` parameter pre-fix at all).

### AC2 — red-then-green, item 108

Reverted `compute_label_geometry`'s face-flag block in
`src/segfacet/features/geometry.py` to the pre-108 hardcoded assignment
(`touches_inferior = bool(x_min_v == 0)`, etc. — the exact six patterns
`test_ac1_no_hardcoded_axis_literal_assignment` searches for), in a scratch
edit never committed. Ran
`.venv/bin/python -m pytest tests/test_108_affine_faces.py::test_ac2_ras_face_named_correctly -v`:
all 6 parametrised cases **FAILED**, each showing the wrong face flagged
true (e.g. box `((0, 3), (2, 5), (2, 5))` — expected only `touches_left` —
reported `touches_inferior=True` instead). Restored the file from a
pre-edit copy; `git status --porcelain` was clean afterward.

### AC3 — red-then-green, item 109

Reverted `compare_runs`'s scale computation in
`src/segfacet/eval/per_mode_cohort.py` to the pre-109 adaptive formula
(`scale = max(abs(value_a - spec.baseline), abs(value_b - spec.baseline))`),
scratch-only. Ran
`.venv/bin/python -m pytest tests/test_109_attribution_scale.py::test_ac7_point_one_vs_point_nine_from_shared_baseline_attributes_to_the_larger_move -v`:
**FAILED** — `d1.normalised_delta` was `1.0` instead of the expected `0.1`
(`AssertionError: assert 1.0 == 0.1 ± 1.0e-07`), the exact saturation
`insights.md` documents. Restored the file; `git status --porcelain` clean
afterward.

### AC4 — red-then-green, item 111

Deleted `tests/golden/022_stage3_report.json` (scratch, never committed).
Ran `.venv/bin/python -m pytest tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot -v`:
**FAILED** with `FileNotFoundError: [Errno 2] No such file or directory:
'.../tests/golden/022_stage3_report.json'` — a hard failure, not a skip,
confirming item 111's fix (the sibling `test_016_features_json.py` test was
already the "fails correctly" precedent this test now matches). Restored the
golden file from a pre-deletion copy; `git status --porcelain` clean
afterward.

### AC5 — border/fov end-to-end (G2)

Ran the real CLI:
`.venv/bin/python -m segfacet.cli run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/mode6_crop_at_border_seg.nii.gz --out <scratch>`
— the committed `mode6_crop_at_border` corpus case, whose
`perturbation_params.face` is `"anterior"` (label 22, `L3`, cropped toward
the anterior face). The emitted report (`segfacet_report.txt`) contains:

```
[flagged-for-review] Partial vertebra clipped by FOV: label 22 (L3) touches image face(s): anterior.
```

under both the per-label findings for label 22 and the `(border)`-tagged
entry in the Findings section — the face named matches the perturbation's
actual crop face exactly, confirming `border`/`fov` name the anatomically
correct face end-to-end on real pipeline output (not just in item 108's unit
tests). This corrects the item spec's own pre-115 wording, which expected a
"cranio-caudal" face for this case; `insights.md` (item 116, 2026-08-13)
already recorded that the designated case has always cropped toward
anterior, unaffected by any Stage 26 fix — non-blocking, the behaviour is
correct.

### AC6 — attribution follows magnitude, both directions (G7)

Built two `RunPerModeSummary` pairs directly through the production
`segfacet.eval.per_mode_cohort` API (`compare_runs`), each holding two
"clean" scan/candidate runs whose bounded modes 1 and 4 both start at
baseline `0.0`:

- **Forward**: mode 1 moves to `0.1`, mode 4 moves to `0.9`. Result:
  `mode1.normalised_delta == 0.1`, `mode4.normalised_delta == 0.9`,
  `attributed_mode == 4` (`semantic mislabelling (wrong identification)`).
- **Reversed**: mode 1 moves to `0.9`, mode 4 moves to `0.1`. Result:
  `mode1.normalised_delta == 0.9`, `mode4.normalised_delta == 0.1`,
  `attributed_mode == 1` (`label not aligned with the vertebra it names`).

Attribution followed the larger normalised move in both directions — not a
single lucky output, and not the mode number. (Replay script kept outside
the repo, under the session scratchpad, not committed; the run is
reproducible from the production API alone, no test-only helper.)

### AC7 — neighbourhood fork, confirmed by suite

`.venv/bin/python -m pytest tests/test_115_stage26_validation.py -k ac7 -v`
— 4/4 passed: `extract_feature_record` populates
`stage3.per_label_neighbourhood`; `catalogue.build_catalogue()` lists those
entries `status: "unwired"` with `consuming_rules == ()`; `progress.md`'s
two Item-024 references both carry the corrected "unwired"/"consumed by no
rule" wording; `pipeline.py`'s source mentions `neighbourhood`. No claim
about it in `progress.md` outruns observable behaviour.

### AC8 — the fence audit

Ran the full `tests/test_115_stage26_validation.py -k "ac8"` sweep (25
tests, all pass) — the AST-based classifier walks every `==` comparison in
`tests/*.py` whose either side derives from `hashlib.sha256(...)` and
resolves the *other* side by name-binding, not by name spelling.

**One fence remains and is not retired here**:
`tests/test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged`,
`_PRE_098_REFERENCE_VERSE_V1_SHA256`, compared against a freshly-computed
digest of `reference_verse_v1.json`. `tests/test_098_stray_components.py` is
not in item 115's `## Authorised paths`, so it cannot be retired here; per
AC8's "retire it or record why it stays" branch, the judgement:
`reference_verse_v1.json` is a released production artifact (80 real
VerSe19 subjects, the CLI's actual default reference since item 090) that
arguably *should* never change silently — pinning its bytes reads more like
a legitimate artifact-integrity invariant than item 107's diff-time "item N
didn't touch file X" claim frozen into a permanent one. The counter-argument
that keeps this from being a clean "it's fine, leave it": the assertion
lives inside a module about stray-component detection, under a `_PRE_098_`
name — a future legitimate regeneration of `reference_verse_v1.json` (a
real re-fit, a corrected ingest) will fire an assertion that reads, out of
context, exactly like a scope violation, in a file that has nothing to do
with the reference artifact's own lifecycle. If the invariant is worth
keeping, it belongs as a named artifact-integrity test living near
`reference/artifact.py`, not here — logged to `insights.md` rather than
acted on (out of this item's scope, AC15).

**Why item 107's own grep missed it**: item 107's AC1 was scoped to five
named item-number prefixes — `_PRE_099_*`, `_PRE_100_*`, `_PRE_101_*`,
`_PRE_103_*`, `_PRE_105_*`, the five items whose fences it was created to
retire — not a generic `_PRE_[0-9]+` sweep across every item number ever
used in `tests/`. `_PRE_098_REFERENCE_VERSE_V1_SHA256` names item 098, which
was never in that five-item list, even though its *shape* is identical to
the five that were retired. `insights.md` already recorded this class of
miss (item 116, 2026-08-12: "the audit needs to search by assertion shape
... rather than by constant name"); this item's AC8 shape-based classifier
is that fix, applied.

**Three intra-run digest assertions correctly survive**, confirmed still
present and still classified `"intra-run"` by
`test_ac8_intra_run_digest_assertions_still_exist`/
`test_ac8_test_102_path_digest_dict_is_intra_run_not_a_fence`/
`test_ac8_test_094_data_sha256_lookup_is_not_a_fence`:
`test_102_stage18_validation.py::test_adv_no_mutation_of_manifests_and_fixtures`
(lines ~692-719, `_SRC_TREE_HASH_AT_COLLECTION` at lines ~830-853, whose
section header still reads "the scope fence" though it is not one — the
name is stale prose, not a defect in the assertion itself, and out of this
item's authorised paths to rename), `test_100_severity_ladder.py:202`, and
`test_094_tptbox_image_layer.py:239-240` (a digest over loaded array bytes
compared against a committed-JSON `data_sha256` value, external rather than
computed-both-ways, but still not a hardcoded literal in the test source —
correctly classified `"external"`, not `"fence"`).

The spec's original AC8 text mis-described
`test_102_stage18_validation.py`'s "path-to-digest dict asserted around line
668" as a second known-remaining fence; corrected above in the Acceptance
Criteria section itself, with the real line numbers and the real
classification (intra-run, not a fence).

### AC9 — authorised paths, confirmed by suite

`.venv/bin/python -m pytest tests/test_115_stage26_validation.py -k ac9 -v`
— 21/21 pass: all ten queue-016 specs (107-116) carry a non-empty
`## Authorised paths` section and `check_item_scope.py`'s own parser reads
each without raising.

### AC10 — the checker catches a real violation

On scratch branch `aide/115-scratch-ac10-violation` (branched from this
item's branch, deleted afterward — never pushed), appended a comment line
to `src/segfacet/pipeline.py`, a file **not** listed in item 115's own
`## Authorised paths`. Ran:

```
.venv/bin/python scripts/check_item_scope.py docs/aide/items/115-validate-stage26.md --base aide/queue-016
```

Output (stderr, exit code 1):

```
src/segfacet/pipeline.py not authorised by docs/aide/items/115-validate-stage26.md
```

`--base aide/queue-016` was used deliberately, not the default `--base
main`: `insights.md` (item 113, 2026-08-15) already documents that `--base
main` is stale on this checkout (local `main` sits at queue-015, ~23 items
behind the live branch) and produces ~90 false positives unrelated to the
item under test. Reverted the scratch edit (`git checkout --
src/segfacet/pipeline.py`), confirmed `git status --porcelain` clean, then
switched back to `aide/115-validate-stage-26-carried-defect` and deleted the
scratch branch (`git branch -D aide/115-scratch-ac10-violation`).

### AC11 — fresh-clone suite run

`git clone` the local checkout
(`/mnt/data/spine/codes/SegFACET`) into a scratch directory whose path
differs from this checkout's (outside the repo entirely, under the
session's scratchpad), checked out
`aide/115-validate-stage-26-carried-defect` there, built a fresh `.venv`
with `python -m venv .venv` + `.venv/bin/pip install -e .[dev]`, and ran
`.venv/bin/python -m pytest -q`.

<!-- AC11_RESULT_PLACEHOLDER -->

Per the spec's own stated limit (Assumptions): a different-directory clone
catches the absolute-path class of bug (item 099's), not the line-ending or
path-separator classes — both checkouts here are on the same Linux
filesystem, so those two classes remain CI's job, not this item's.

### AC13 — verification rows

`python .aide/scripts/aide.py env --profile docker` and `--profile
pyradiomics` both report **not satisfied** in this execution environment (no
`docker` daemon, no `radiomics` package installed) — exit 1 on both, so no
row can be honestly flipped to ✅ Verified from *this* run. Both the Docker
and PyRadiomics Environment-Gated Capability Verification rows were already
✅ Verified (2026-07-14, GitHub Actions CI) before this item and are left
unchanged. Confirmed item 113 did not flip the Docker row by reducing where
Docker runs: `.github/workflows/ci.yml`'s `verify-environment-gated` job
(the one that actually verifies Docker) is untouched by item 113, which only
scoped the separate `test-numpy-majors` job's collection away from the
Docker-/PyRadiomics-gated modules — confirmed by
`tests/test_115_stage26_validation.py::test_ac13_docker_verification_row_evidence_date_unchanged_by_item_113`
(pins the original 2026-07-14/GitHub-Actions-CI evidence) and
`::test_ac13_docker_verification_row_status_still_verified`, both passing.

### AC14 — `aide check`

`python .aide/scripts/aide.py check` reports **OK (9 warning(s))** —
identical to the documented baseline (progress.md:340/459/638,
queue-002.md:80, insights.md:51/58/60, two stale-claim-branch warnings) both
before and after every `progress.md`/`insights.md`/item-spec edit made in
this item. No new "status icon outside a structural status position"
warning was introduced by the acceptance-box evidence annotations (none of
them use a bare ✅/❌/🚧 icon).

### AC15 — findings logged, not fixed

Four findings from this replay that are not Stage 26 deliverables were
appended to `insights.md` rather than acted on: (1) the second live instance
of the `aide progress set` force-tick defect (item 114's entry), now hitting
Stage 26's honestly-unticked fifth acceptance box; (2) the mechanism behind
why item 107's grep missed `_PRE_098_REFERENCE_VERSE_V1_SHA256`
(scoped-by-item-list grep, not a shape sweep); (3) the judgement that
`reference_verse_v1.json`'s byte-pin might be a legitimate artifact-integrity
invariant misplaced in an unrelated test module, and should become a
properly-named test elsewhere rather than being fixed inline; (4) the
`test_102_stage18_validation.py` section-header wording ("the scope fence")
that is stale now that item 107 retired the actual fences, left
unrenamed since that file is outside this item's authorised paths.

### Assumptions restated

Per the item's own Assumptions: red-then-green was staged in a scratch tree
for AC2/AC3/AC4 only, never on the branch, and every revert was restored
with `git status --porcelain` confirmed clean immediately after. Items 107,
110, 112, 113, 114 and 116 were verified by inspection of their own
committed, already-passing regression tests rather than by re-breaking them
— re-breaking any of the six means deleting a script, unwiring a module,
editing CI, or reverting a whole-corpus migration, disproportionate to the
evidence gained over reading tests already proven to pin the fix. The AC11
different-directory clone is the available proxy for a different platform,
catching only the absolute-path bug class; the spec records that limit
explicitly rather than implying broader coverage.

### Stage 26 acceptance boxes — honest tick, and a known force-tick collision

Of Stage 26's five acceptance boxes (`progress.md:1061-1068`), four are
ticked with an evidence annotation based on the replays above. The fifth
("No `_PRE_NNN_*` byte-hash fence remains...") is left **honestly unticked**
with a reason: one `_PRE_NNN_*`-named fence
(`_PRE_098_REFERENCE_VERSE_V1_SHA256`) still remains, outside this item's
authorised paths to retire, even though the checker's own
out-of-scope-detection half is independently verified (AC10). Per the task's
own instruction and `insights.md`'s existing force-tick entry (item 114,
2026-08-15): once a later `aide progress set 115 done` call makes Stage 26's
rollup derive "complete" (once item 115's own deliverable bullet flips to
✅), `_tick_acceptance` will force this fifth box to `- [x]` regardless of
this honest assessment — a second live instance of that framework defect,
now logged in `insights.md` rather than silently accepted as a real
re-verification.
