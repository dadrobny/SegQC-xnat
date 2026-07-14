# Item 076 — PyRadiomics present-path graceful degrade on a too-small/degenerate mask

> **Created:** 2026-07-14 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features
> **Queue:** retroactive Stage-8 bug-fix — not part of a numbered queue; registered directly in [`progress.md`](../progress.md) (Stage 8, item 076) and [`roadmap.md`](../roadmap.md). Fixes a defect in Item 060 (delivered by [`../queue/queue-007.md`](../queue/queue-007.md)), discovered post-completion by a new CI job.
> **Objectives:** G6 (portable execution — a heavy/finicky optional lib is never *required*, and now degrades cleanly even when present-but-unable to handle a given mask); supports the §9 **Robustness** NFR ("tolerant of ... partial/border vertebrae ... without crashing") and G7 (regression-testable).
> **Suggested branch:** `aide/076-radiomics-degenerate-mask-graceful-degrade`

---

## Description

**Targeted bug fix** to the optional PyRadiomics adapter
`src/segqc/features/radiomics.py` (item 060). This is **not** a feature — it adds
exactly one graceful-degradation guard and changes no other behaviour.

**The bug.** `compute_label_radiomics` already degrades to the builtin
(first-order-only) result when a label is **empty/absent**
(`first_order.voxel_count == 0`, lines ~274–277): PyRadiomics is never handed a
zero-voxel mask because it would error. But there is **no equivalent guard for a
non-empty yet too-small/geometrically-degenerate mask** — e.g. a single-voxel
label, or a paper-thin `(1,1,8)` sliver. For such a mask the code calls
`_extract_with_pyradiomics(...)` (line ~279) directly, and PyRadiomics's **own**
geometry validation rejects the mask, raising a raw `ValueError` (e.g. *"No labels
found in this mask (i.e. nothing is segmented)!"* or *"mask only contains 1
segmented voxel! Cannot extract features for a single voxel."*). That `ValueError`
propagates straight out of `compute_label_radiomics`, uncaught — breaking the
module's own stated "degrade cleanly" philosophy (docstring lines ~66–75, which
today only covers the empty-mask case).

This was invisible until a new CI job (`.github/workflows/ci.yml`'s
`verify-environment-gated` job, on the still-unmerged sibling branch
`ci/verify-environment-gated-capabilities`, PR #33) installed the **real**
`pyradiomics` on `ubuntu-latest` for the first time and ran
`tests/test_features_radiomics.py`. **7 tests** that build tiny masks with the
default `enable_pyradiomics=True` failed with that raw `ValueError`.

**The fix.** Catch PyRadiomics's own geometry-validation failure at the extraction
call site and degrade to the builtin result — mirroring the existing empty-mask
degrade exactly. A mask too small/degenerate for PyRadiomics's shape/GLCM classes
is functionally *"PyRadiomics could not contribute extended features for this
call"*, so it must carry the same builtin markers as the empty-mask and
absent-library paths.

**In scope:** one guard around the `_extract_with_pyradiomics(...)` call inside
`compute_label_radiomics`, degrading to `_builtin_result(first_order)` on
PyRadiomics's geometry-validation `ValueError`; a one-line docstring update
extending the documented degrade philosophy to the too-small/degenerate case.

**Explicitly NOT in scope:** any change to the empty-mask path, the absent-library
path, the `enable_pyradiomics=False` disable path, `_extract_with_pyradiomics`'s
own body (array construction, extractor settings, key filtering), the alignment
guard, `compute_radiomics_features`, the `pyproject.toml` `radiomics` extra, or
any other module. No new features, no changed output shape, no threshold/heuristic
logic.

## Acceptance Criteria

_Each criterion is atomic and directly testable. AC1–AC4 and AC7–AC8 are covered
by tests that **already exist** in `tests/test_features_radiomics.py` and must pass
once the production fix lands and PyRadiomics is genuinely present (no test-logic
change). AC5–AC6 are regression guards over already-passing behaviour. See Testing
Strategy for the AC→test mapping and the one small additive assertion AC3 needs._

- [ ] **AC1: Degenerate/too-small non-empty mask does not raise (present path).**
  With PyRadiomics genuinely importable (`pyradiomics_available() is True`),
  `compute_label_radiomics(scan_img, seg_img, label, enable_pyradiomics=True)` on a
  **non-empty** mask (`first_order.voxel_count > 0`) that PyRadiomics's own
  geometry validation rejects as too small/degenerate for the enabled shape/GLCM
  classes — e.g. a single-voxel label, or the `(1,1,8)` sliver of
  `_known_values_case()` — returns a `LabelRadiomics` and propagates **no**
  exception (previously raised `ValueError`).

- [ ] **AC2: Degenerate-mask result is a valid, complete `LabelRadiomics`.** In
  that case the returned object is a frozen `LabelRadiomics` with all four
  documented fields present and correctly typed (`first_order: LabelIntensity`,
  `extended: dict`, `backend: str`, `radiomics_available: bool`), and
  `result.first_order` is **exactly equal** to
  `compute_label_intensity(scan_img, seg_img, label)` for the same inputs.

- [ ] **AC3: Degenerate-mask degrade mirrors the empty-mask degrade (builtin
  markers).** In that case `result.extended == {}`,
  `result.backend == RADIOMICS_BACKEND_BUILTIN` (`"builtin"`), and
  `result.radiomics_available is False` — identical to the empty-mask
  (`voxel_count == 0`) and absent-library degrade, consistent with the documented
  meaning of `radiomics_available` ("whether PyRadiomics actually produced
  `extended` for this call").

- [ ] **AC4: Determinism & purity preserved on the degenerate present path.** Two
  identical `compute_label_radiomics` calls on a degenerate-mask input compare
  equal (`==`), and neither call mutates the scan or segmentation image array data
  (arrays byte-identical before and after).

- [ ] **AC5: Empty/absent-label behaviour unchanged (regression).** For an absent
  label or an all-background mask (`voxel_count == 0`), behaviour is exactly as
  before item 076: sentinel `first_order`, `extended == {}`, builtin markers, no
  exception — and the PyRadiomics wrapper is still **not** invoked on a zero-voxel
  mask.

- [ ] **AC6: Absent-library and explicit-disable behaviour unchanged
  (regression).** With PyRadiomics absent, or with `enable_pyradiomics=False`, the
  builtin path is taken exactly as before (`extended == {}`, builtin markers, no
  exception); the new guard adds no observable behaviour on these paths.

- [ ] **AC7: Healthy present-path extraction still succeeds (regression).** For a
  mask large enough for PyRadiomics (e.g. `_blob_case_for_present_path()`'s
  `4×4×4` cube), the present path still yields a **non-empty** `extended`,
  `backend == "pyradiomics"`, `radiomics_available is True`, and unchanged
  `first_order` — the new guard does **not** swallow successful extractions.

- [ ] **AC8: Guard scope is narrow — genuine input errors still surface
  (regression).** A scan/segmentation pair with mismatched shape or incompatible
  affine still raises `ValueError` (guarded upstream by `compute_label_intensity`
  before the PyRadiomics wrapper is ever reached), on both the builtin and present
  paths — the new degrade guard does not mask alignment/shape-mismatch errors.

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): the item was
  already fully investigated; no blocking questions. Each defensible default is
  pinned below for validator audit.
- **Exception type to catch (pin — key decision).** PyRadiomics raises a plain
  `ValueError` (from `radiomics.imageoperations`/mask-validation, e.g. `checkMask`)
  for both *"No labels found in this mask"* and *"mask only contains 1 segmented
  voxel"*; there is **no** dedicated PyRadiomics exception subclass for these
  geometry validations. The narrowest robust catch is therefore **type-based
  `ValueError`** at the extraction call — **not** message-string matching (brittle
  across PyRadiomics versions).
- **Why catching `ValueError` broadly here is safe (pin).** By the time
  `_extract_with_pyradiomics(...)` is reached, (a) the scan↔seg **alignment/shape**
  guard has already fired — it runs inside `compute_label_intensity` *before* the
  wrapper, so a mismatch raises there and never reaches the catch (AC8); and (b)
  the **empty-mask** case (`voxel_count == 0`) is already short-circuited to the
  builtin result before the wrapper. Hence the only `ValueError` reachable at the
  extraction call is a **legitimate PyRadiomics geometry-validation rejection of a
  valid-but-degenerate mask** — catching it cannot mask a segqc alignment/shape
  bug.
- **Guard placement & degrade target (pin).** Wrap **only** the
  `_extract_with_pyradiomics(scan_img, seg_img, label)` call in
  `compute_label_radiomics` in a `try/except ValueError`, and on catch return
  `_builtin_result(first_order)` — the exact same object the empty-mask branch
  returns (`extended={}`, `backend="builtin"`, `radiomics_available=False`). The
  `try` must be tight around the extraction call only, so a genuine bug elsewhere
  (e.g. in `_extract_with_pyradiomics`'s SimpleITK array construction, or in
  `compute_label_intensity`) still surfaces rather than being silently degraded.
- **Scope pin.** The change touches only `compute_label_radiomics`'s call to
  `_extract_with_pyradiomics` plus a docstring note. It does **not** change the
  empty-mask path, the absent-library path, the disabled path,
  `_extract_with_pyradiomics`'s body, or `compute_radiomics_features`.
- **Windows-local validation limitation (pin — validator must surface).**
  PyRadiomics's prebuilt Windows wheel fails to **import** on this dev machine
  (`ImportError: numpy.core.multiarray failed to import` — an ABI mismatch against
  numpy 2.x, unrelated to this bug), so `pyradiomics_available()` returns `False`
  locally regardless. Consequently **the present-path fix cannot be validated
  end-to-end on Windows**: all present-path tests `pytest.importorskip("radiomics")`
  and skip, so a local `pytest` run stays green **without** exercising the fix — a
  skip-clean run does **not** count as verification (per `.aide/conventions.md`'s
  Environment-Gated Capability rule). True confirmation requires either (a) a
  Linux/CI environment where `pyradiomics` builds from source against the installed
  numpy (what the CI job that found this bug did), or (b) a locally source/MSVC-built
  `pyradiomics` (no compiler available; not attempted). Final sign-off = re-running
  the sibling `ci/verify-environment-gated-capabilities` job (PR #33) after this fix
  merges.
- **No-test-change hypothesis (pin).** The 7 currently-failing tests encode the
  correct intent and need **no logic change** — they pass once the production guard
  lands and PyRadiomics is genuinely present. The only optional adjustment is a
  small **additive** assertion for AC3's builtin-marker semantics on the existing
  degenerate present-path test (`test_adv_single_voxel_label_present_path_does_not_crash`),
  or a tiny dedicated test — neither alters any of the 7 tests' existing logic.
- **Dependency interfaces unchanged (pin).** Item 060's
  `src/segqc/features/radiomics.py` still exposes `compute_label_radiomics`,
  `_extract_with_pyradiomics`, `_builtin_result`, `RADIOMICS_BACKEND_BUILTIN`, and
  the `first_order.voxel_count` field on item 059's `LabelIntensity`, exactly as
  read for this spec. The `pyproject.toml` `radiomics = ["pyradiomics>=3.0"]` pin is
  unchanged; the `ValueError` behaviour holds across that pinned range. If any
  diverged, hand back.

## Implementation Steps

_Intended code path under `src/segqc` (`aide.toml` `source_dir = "src/segqc"`).
Single file: `src/segqc/features/radiomics.py`._

1. **`compute_label_radiomics` (lines ~269–286).** Leave the existing branches
   unchanged: the `not (enable_pyradiomics and pyradiomics_available())` builtin
   branch, and the `first_order.voxel_count == 0` empty-mask builtin branch both
   stay exactly as-is.
2. **Guard the extraction call.** Replace the current unconditional
   `extended = _extract_with_pyradiomics(scan_img, seg_img, label)` (line ~279)
   with a tight `try/except ValueError` that, on catch, returns
   `_builtin_result(first_order)` — the same degrade the empty-mask branch uses.
   On success, build and return the `LabelRadiomics(..., backend=PYRADIOMICS,
   radiomics_available=True)` result exactly as today. Keep the `try` scoped to the
   extraction call **only** (do not wrap `first_order` computation or the success
   `return`), so unrelated errors still propagate.
3. **Add a short explanatory comment** at the guard mirroring the existing
   empty-mask comment, e.g. *"Non-empty but too-small/degenerate mask: PyRadiomics'
   own geometry validation may reject it (ValueError). Degrade to the builtin
   markers, exactly like the empty-mask case — never let PyRadiomics' rejection
   propagate."*
4. **Extend the module docstring** — the "Empty/absent label & alignment guards"
   section (lines ~66–75) — with one sentence noting that a **non-empty but
   too-small/degenerate** mask that PyRadiomics rejects is likewise degraded to the
   builtin result (not raised), so the documented "degrade cleanly" philosophy now
   covers both the empty and the degenerate case.
5. **Touch nothing else.** No change to `_extract_with_pyradiomics`,
   `compute_radiomics_features`, `_builtin_result`, the dataclass, constants,
   `pyproject.toml`, or any other module.

## Testing Strategy

_Test module: `tests/test_features_radiomics.py` (item 060's existing suite). The
present-path tests are guarded by `pytest.importorskip("radiomics")` and only run
where PyRadiomics is genuinely importable — i.e. Linux/CI, **not** this Windows dev
box (see the Windows-local limitation in Assumptions)._

**AC → existing test mapping (all already written; must pass unchanged once the
fix lands and PyRadiomics is present):**

- **AC1** — `test_ac9_aligned_inputs_do_not_raise` (the `(1,1,8)` sliver) and
  `TestPresentPath::test_adv_single_voxel_label_present_path_does_not_crash`
  (1-voxel label). Both currently raise `ValueError`; must return normally.
- **AC2** — `test_ac3_label_radiomics_is_frozen_dataclass_with_documented_fields`,
  `test_ac3_field_types_are_json_friendly`, `test_ac3_comparable_with_equality`,
  and the `first_order` equality assertion in
  `test_adv_single_voxel_label_present_path_does_not_crash`.
- **AC3** — the builtin-marker semantics are **not** currently asserted for the
  degenerate case. Cover it with a **small additive** assertion on the existing
  `test_adv_single_voxel_label_present_path_does_not_crash`
  (`result.extended == {}`, `result.backend == "builtin"`,
  `result.radiomics_available is False`), or a tiny dedicated present-path test.
  This is additive and preserves that test's intent; it does **not** touch the 7
  must-pass tests' existing logic.
- **AC4** — `test_ac11_determinism_repeated_calls_equal` and
  `test_ac11_compute_label_radiomics_does_not_mutate_inputs` (both on the
  `(1,1,8)` sliver).
- **AC5** — `test_ac10_absent_label_returns_sentinel_first_order_and_empty_extended`,
  `test_ac10_all_background_mask_returns_sentinel_no_exception`,
  `test_ac10_empty_label_holds_with_pyradiomics_enabled_too` (regression: still
  degrade, wrapper still not invoked on zero-voxel mask).
- **AC6** — `test_ac5_absent_path_yields_builtin_markers_and_no_exception`,
  `test_ac6_enable_pyradiomics_false_forces_builtin_path`,
  `test_adv_enable_true_with_pyradiomics_absent_still_degrades_cleanly`
  (regression: absent/disabled paths unaffected).
- **AC7** — `TestPresentPath::test_ac12_extended_is_nonempty_documented_glcm_shape_subset`,
  `test_ac13_present_path_backend_and_availability_markers`,
  `test_ac14_present_path_determinism` (regression: the guard must not swallow the
  healthy `4×4×4`-blob extraction).
- **AC8** — `test_ac9_shape_mismatch_raises_value_error_on_builtin_path`,
  `test_ac9_affine_mismatch_raises_value_error_on_builtin_path`,
  `test_ac9_shape_mismatch_raises_with_pyradiomics_enabled_too` (regression:
  alignment/shape mismatch still raises `ValueError`, upstream of the wrapper).

**Adversarial / edge cases (already represented in the suite):** single-voxel
label (`5×5×5` with one voxel set), `(1,1,8)` 1-D sliver, all-background mask,
absent-label sentinel, mismatched shape, mismatched affine, healthy solid blob,
determinism (two identical calls), and input immutability (`.copy()` snapshots).
Together these bound the fix: it must degrade **only** on PyRadiomics's own
geometry rejection of a valid-but-degenerate non-empty mask, never on a healthy
extraction (AC7) and never masking an alignment error (AC8).

**Local-validation gap (explicit).** On this Windows dev host,
`pyradiomics_available()` is `False`, so every present-path test **skips** and a
local `pytest` run is green **without** exercising the fix. That green run is
**not** verification. The validator must record the fix as verified only after the
Linux/CI present-path run (sibling branch `ci/verify-environment-gated-capabilities`
/ PR #33) executes these tests with PyRadiomics installed and they pass.

## Dependencies

- **Item 060 — Optional PyRadiomics integration (✅).** The module being fixed:
  `src/segqc/features/radiomics.py`. Provides `compute_label_radiomics`,
  `_extract_with_pyradiomics`, `_builtin_result`, the `LabelRadiomics` dataclass,
  the backend constants, and the existing empty-mask degrade this fix mirrors.
- **Item 059 — Per-label first-order intensity extractor (✅).**
  `src/segqc/features/intensity.py` provides `compute_label_intensity` /
  `LabelIntensity` (the authoritative `first_order` block and its `voxel_count`
  sentinel) and the `_check_alignment` guard whose **early** firing (inside
  `compute_label_intensity`, before the PyRadiomics wrapper) is exactly what makes
  catching `ValueError` at the extraction call safe (AC8).

## Environment / Hardware Dependencies

- **`pyradiomics`** (PyPI `pyradiomics`, import name `radiomics`) — declared via the
  `pyproject.toml` `radiomics` optional extra (`pip install segqc[radiomics]`), not
  a core dependency. Required fallback: when absent **or** when present-but-unable
  to handle a given mask, `compute_label_radiomics` must degrade cleanly to the
  builtin first-order result (this item adds the "present-but-unable" half of that
  contract). **Full-capability verification:** this item is precisely what first
  drives the real present path under CI. The capability is already tracked by the
  existing **"Radiomics feature extraction"** row (introduced by Item 060) in
  `progress.md`'s *Environment-Gated Capability Verification* table, currently
  `❓ Unverified`. That row stays `❓ Unverified` on Windows-local (import fails,
  present-path tests skip); it flips to `✅ Verified` only when the sibling
  `ci/verify-environment-gated-capabilities` job (PR #33) runs the present-path
  tests with `pyradiomics` genuinely installed and they pass. Per the hard limits,
  the builder/validator reconcile that table via the `aide` CLI — this spec does
  not edit `progress.md`.

## Decisions & Trade-offs

**Implemented exactly per the pinned plan.** In `compute_label_radiomics`
(`src/segqc/features/radiomics.py`), the previously-unconditional
`extended = _extract_with_pyradiomics(scan_img, seg_img, label)` line is now
wrapped in a tight `try/except ValueError` that, on catch, `return
_builtin_result(first_order)` — the identical degrade the empty-mask branch
above it already uses. The `try` scopes only the extraction call itself; the
subsequent `LabelRadiomics(..., backend=RADIOMICS_BACKEND_PYRADIOMICS,
radiomics_available=True)` success-path construction/return sits outside the
`try` block entirely, so it cannot accidentally swallow an error from
somewhere else. A comment at the guard explains the rationale (mirrors the
existing empty-mask comment's style). No other branch, function, or the
`_extract_with_pyradiomics` body was touched.

The module docstring's "Empty/absent label & alignment guards" section
(lines ~66–75) gained one added sentence noting that a non-empty but
too-small/degenerate mask rejected by PyRadiomics' own geometry validation is
likewise degraded to the builtin result (citing item 076), so the documented
"degrade cleanly" philosophy now explicitly covers both the empty-mask and
degenerate-but-nonempty cases.

No test files were modified by this agent (test-writer already committed the
one additive assertion). Could not exercise the present path locally
(PyRadiomics fails to import on this Windows dev machine per the spec's pinned
Windows-local limitation); correctness was verified by careful reading against
the spec's AC1–AC8 and by confirming the diff matches the Implementation Steps
verbatim. Final present-path verification happens via the sibling CI job (PR
#33) per the spec.
