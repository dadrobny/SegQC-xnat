# Item 112 — `compute_per_mode_metrics(overlap_result=…)` short-circuit

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 112
> **Objectives:** G7
> **Suggested branch:** `aide/112-overlap-short-circuit`

---

## Description

Add an optional `overlap_result=None` keyword to
`src/segfacet/eval/per_mode.py::compute_per_mode_metrics` that skips the
internal `compute_overlap` call when the caller already holds the result, and
pass it from `eval/harness.py::evaluate_case`.

The harness computes exactly that `OverlapResult` for its own `overlap` field
(`harness.py:407`) immediately before item 101's `per_mode=True` hook calls
`compute_per_mode_metrics` on the same three inputs — candidate array, GT array
and spacing — so every per-mode cohort run pays a second full pass over the
label map per case. Item 101 accepted the duplicate rather than widen an API
that items 099/100 had frozen behind byte-hash fences; this item is where that
is legitimately open.

**In scope.** The optional keyword, the harness call site, and the documented
contract for what a caller-supplied result must be.

**Not in scope.** Changing what `compute_per_mode_metrics` computes or returns.
Changing `compute_overlap`. Any change to `per_mode_cohort.py` (item 109 owns
that file this stage). Performance work anywhere else.

## Acceptance Criteria

- [ ] **AC1: the keyword exists and defaults to `None`.**
  `compute_per_mode_metrics(..., overlap_result=None)` is accepted, and the
  default path is exactly today's behaviour.
- [ ] **AC2: results are identical either way.** For the same inputs, the
  returned `PerModeMetrics` is equal whether `overlap_result` is supplied or
  computed internally.
- [ ] **AC3: the internal call is genuinely skipped.** With a result supplied, a
  spy on `compute_overlap` records zero calls from within
  `compute_per_mode_metrics`.
- [ ] **AC4: the harness passes it.** `evaluate_case` supplies its existing
  `OverlapResult`, and a spy confirms `compute_overlap` is called **once** per
  case through the harness where it was previously called twice.
- [ ] **AC5: harness output is unchanged.** Every field of the harness's
  per-case and cohort output is identical to pre-change on the corpus.
- [ ] **AC6: a mismatched result is rejected cheaply.** When the supplied
  `OverlapResult` does not correspond to the given inputs — detectable by a
  cheap invariant such as label-set or shape disagreement — the function raises
  a clear error naming the mismatch rather than silently returning wrong
  numbers.
- [ ] **AC7: the cheap check is documented as not exhaustive.** The docstring
  states which invariants are verified and that a caller supplying a
  same-shape-but-wrong result is trusted, so the contract is explicit rather
  than implied.
- [ ] **AC8: no other call site changes behaviour.** Every existing caller of
  `compute_per_mode_metrics` that does not pass the keyword is untouched and
  produces identical output.

## Assumptions

- **Cheap validation over blind trust** (spec-author default). The queue left
  "reject or document as caller-trusted" open; rejecting on a shape/label-set
  mismatch costs nothing and turns a silent wrong-number failure into a loud
  one, which is the same principle item 111 applies to a missing golden. Deep
  verification (recomputing to compare) would defeat the purpose and is
  explicitly not done.
- **`OverlapResult` carries enough to validate cheaply** — at minimum the label
  sets or array shapes it was computed from. If it does not, AC6 is satisfied by
  the weakest available invariant and the gap is recorded in Decisions rather
  than by adding fields to `OverlapResult` (out of scope).
- **`eval/per_mode.py` is this item's to edit.** Item 109 was told to hand back
  rather than touch it; if both items need it, coordinate rather than racing.

## Implementation Steps

1. Add the keyword to `compute_per_mode_metrics`, defaulting to `None`; when
   `None`, call `compute_overlap` exactly as today.
2. When supplied, run the cheap invariant check, then use the supplied result
   everywhere the internal one was used.
3. Update the docstring per AC7, naming the checked invariants.
4. Pass the existing `OverlapResult` from `evaluate_case`.
5. Run the corpus through the harness and diff the output against pre-change.

## Testing Strategy

New module `tests/test_112_overlap_short_circuit.py`:

- AC1/AC2: same inputs both ways, assert equality field by field.
- AC3/AC4: monkeypatch `compute_overlap` with a counting wrapper; assert 0 calls
  inside the function with a supplied result, and exactly 1 per case through the
  harness.
- AC5: harness run over corpus cases, output compared to pre-change values.
- AC6: supply a result computed from differently-shaped or differently-labelled
  inputs; assert the error and its message.
- AC7: assert the docstring names the checked invariants.
- AC8: call every existing call site without the keyword and compare.

Adversarial: `overlap_result=None` passed explicitly; a result for an empty
label map; a result computed with different spacing (documented behaviour); the
same result object reused across two calls (must not be mutated).

## Validation

Run the Stage-7 harness over the committed corpus with per-mode enabled, before
and after, and record both the identical output and the halved
`compute_overlap` call count.

## Dependencies

None.

**Downstream:** this item owns the only authorised change to `eval/per_mode.py`
this stage; item 109 defers to it. Neither blocks the other — the note sits
after the marker so `aide claim` does not read it as a dependency.

## Authorised paths

- `src/segfacet/eval/per_mode.py`
- `src/segfacet/eval/harness.py`
- `tests/test_112_overlap_short_circuit.py`
- `docs/aide/items/112-per-mode-overlap-short-circuit.md`

## Decisions & Trade-offs

- **Cheap invariant chosen: label set + per-label voxel-count shape.**
  `_validate_overlap_result` (per_mode.py) checks two things, both O(voxels)
  single-pass work -- cheaper than the O(voxels x labels) work
  `compute_overlap` itself does: (1) the set of label values
  `overlap_result.per_label` covers equals `set(candidate) | set(gt)` minus
  background, and (2) each entry's `candidate_voxels`/`gt_voxels` equals the
  actual per-label voxel count in the given `candidate`/`gt` arrays (the
  proxy for "this came from arrays of this shape/content", since
  `OverlapResult` stores no shape field of its own -- Assumption 2). Neither
  check touches `dice`/`jaccard`/`intersection_voxels`, so a same-shape,
  same-label-set but otherwise-wrong result is trusted verbatim past this
  point (AC7).
- **The undetectable shape mismatch is exactly the harmless one.** The
  invariant catches any shape difference that changes what is being compared,
  because a trim that removes foreground changes a per-label voxel count. What
  it cannot detect is a shape difference confined to an **all-background**
  region -- and in that case `compute_overlap` returns a
  `dataclasses.asdict`-identical result anyway, because background is excluded
  from the comparison by design (`compute_overlap`'s own docstring). So the
  "undetectable" case is one where accepting the supplied result is not merely
  safe but correct: there is nothing to detect. No function of
  `overlap_result` plus the given arrays could distinguish those two calls
  without recomputing the full overlap, which AC6 explicitly forbids.
- **The AC6 shape-mismatch fixture was rebuilt to test what its name claims
  (orchestrator, 2026-08-14).** As first written it sliced `candidate[:-1]` /
  `gt[:-1]`, but the corpus pair's foreground bounding box ends at index 63 of
  a 66-long axis 0, so that trim removed only background -- the "wrong" result
  was identical to the right one and no implementation could have rejected it.
  The builder found this by direct execution, correctly refused both to edit
  the test and to add a shape field to `OverlapResult` (out of scope), and
  recorded it rather than declaring success. The fixture now cuts at index 50,
  which provably removes foreground from both arrays while leaving the label
  set unchanged, so the test isolates a shape/voxel-count disagreement and
  leaves label-set disagreement to its sibling. It asserts those preconditions
  inline, so it cannot silently regress into a no-op trim again.
