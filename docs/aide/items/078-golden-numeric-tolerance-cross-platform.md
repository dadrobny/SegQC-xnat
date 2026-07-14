# Item 078 — Cross-platform golden comparison: numeric tolerance for fresh-vs-committed

> **Created:** 2026-07-14 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (retroactive fix to item 042)
> **Suggested branch:** `aide/078-golden-numeric-tolerance-cross-platform`

---

## Description

Fix a cross-platform floating-point reproducibility limitation in item 042's
golden-file harness, discovered when this repo got its first CI (items 077 /
PR #33): `tests/test_042_golden_determinism.py`'s **fresh-vs-committed**
byte-identity assertions fail on Linux and macOS while passing on Windows,
because the committed golden files (`tests/corpus/golden/*.json`) were
generated on Windows and encode **full-precision floats** whose last ~1 ULP
differs across platforms — even at *identical* numpy/scipy versions
(confirmed: the failures persist under item 077's `constraints.txt` pin, which
fixed the genuine version-drift in items 045/063 but cannot touch this).

**Root cause (fully diagnosed).** Three of the nine corpus cases —
`mode3_inject_islands`, `mode6_crop_at_border`, `mode8_force_overlap` —
perturb the synthetic spine into an *asymmetric / off-plane* geometry that
makes some part of the feature pipeline produce irrational-decimal floats: an
off-grid centre-of-mass (`inject_islands`: label 22 centroid
`106.9841827768014` vs the clean `107.0` of every symmetric case), or
spline-fit / curvature / EDT values once a vertebra drops off the clean plane
(`crop_at_border`, `force_overlap`). The other six cases stay symmetric /
planar and produce exact half-integers (`27.0`, `29.5`) that serialise
bit-identically anywhere. Those irrational floats differ by ~1 ULP between the
Windows machine the goldens were committed from and the Linux/macOS CI
runners (platform BLAS / SIMD / libm rounding), which a raw-byte JSON
comparison flags as a mismatch. This is a genuine limitation of byte-exact
golden files of floating-point data across platforms, not a version or a
`core.autocrlf` issue.

**Fix (human-confirmed decision).** Relax the **fresh-vs-committed** golden
comparisons (AC9's `check_case_golden`, and AC13's regenerated-vs-committed
check) from raw byte-identity to a **recursive numeric-tolerance** comparison:
parse both sides and compare floats with `math.isclose(rel_tol, abs_tol)`,
everything else (structure, keys, strings, ints, bools, `null`, ordering of
lists) exactly. The committed goldens are **not** regenerated — they are
numerically within tolerance of fresh output on every platform, so they stay
untouched (no `.gitattributes` / byte-reproducibility churn).

**What stays strictly byte-exact (deliberately unchanged).** The
**same-platform determinism** guarantees — AC4 (two successive builds are
byte-identical canonical JSON), AC5 (canonical form is a parse/recanonicalise
fixed point), and AC12 (`main` regen equals a fresh in-process build) — remain
raw-byte comparisons. Those compare two builds produced in the *same process
on the same platform*, where byte-identity is both achievable and the correct,
stronger guarantee; they pass on every platform already and this item does not
weaken them. Only the *cross-platform* fresh-vs-committed checks move to
tolerance, because cross-platform byte-identity of these floats was never
actually achievable — item 042's original "equals the committed golden bytes"
wording was, in effect, a single-platform guarantee.

## Acceptance Criteria

- [ ] **AC1: `reports_close` comparator exists.** `segqc.synth.golden` exposes
  `reports_close(a, b, *, rel_tol=..., abs_tol=...) -> bool` (also re-exported
  from `segqc.synth`), recursively comparing two parsed report structures:
  numeric leaves via `math.isclose`, and dict keys / list lengths+order /
  strings / bools / `None` / int-vs-int exactly.
- [ ] **AC2: floats within tolerance compare equal.** Two reports differing
  only by a sub-tolerance float delta (e.g. `106.9841827768014` vs
  `106.98418277680141`) return `True`.
- [ ] **AC3: floats beyond tolerance compare unequal.** A meaningful numeric
  difference (e.g. a centroid off by `0.5`) returns `False`.
- [ ] **AC4: non-numeric differences are exact.** A differing string
  (`verdict` `"pass"` vs `"fail"`), a differing bool, a missing/extra dict key,
  a differing list length, or a reordered list all return `False` — booleans
  are **not** treated as numbers (`True` != `1.0`).
- [ ] **AC5: `check_case_golden` uses tolerance.** `check_case_golden(case)` is
  `True` for every committed case via `reports_close` (parsed fresh vs parsed
  committed), and still propagates `FileNotFoundError` when the golden is
  absent (AC14 behaviour preserved) and still returns `False` for a mutated
  `verdict` (AC15 behaviour preserved).
- [ ] **AC6: AC9 passes on every platform.**
  `test_ac9_fresh_canonical_json_equals_committed_golden_bytes` passes for all
  nine cases (the three previously-failing asymmetric modes included) — the
  cross-platform proof is the CI run on ubuntu/windows/macos, since it cannot
  be reproduced on a single local platform.
- [ ] **AC7: AC13 uses tolerance and passes on every platform.**
  `test_ac13_regeneration_reproduces_committed_goldens_byte_for_byte` compares
  regenerated-vs-committed via `reports_close` and passes on all three OSes.
- [ ] **AC8: same-platform determinism stays byte-exact.** AC4/AC5/AC12's
  byte-identity assertions are unchanged and still pass (regression guard —
  this item must not weaken the same-platform guarantee).

## Assumptions

- **A1 — Committed goldens are not regenerated.** They are numerically within
  tolerance of fresh output on every platform (the deltas are ~1 ULP), so
  leaving them as-is is correct and avoids byte-reproducibility churn. If any
  case's delta were ever *beyond* tolerance, that would be a real regression
  the tolerance must still catch (AC3), not something to paper over by
  re-committing.
- **A2 — Tolerance values.** `rel_tol=1e-9, abs_tol=1e-12` — loose enough to
  absorb cross-platform ULP noise on values ranging from `~1e-14`
  (`total_curvature_deg`) to `~200` (centroids in mm), tight enough that any
  genuine feature change (the smallest meaningful deltas these tests guard are
  ≫ 1e-9 relative) is still caught. Finalised during implementation against
  the actual committed values.
- **A3 — Only `check_case_golden` and AC13 change semantics.**
  `check_case_golden` is consumed solely by test_042 (verified). AC4/AC5/AC12
  keep `canonical_json` byte-equality. `canonical_json`/`write_goldens`/`main`
  are unchanged.
- **A4 — CI is the only real validator.** This fix cannot be validated on a
  single platform (it passes locally on Windows today *because* the goldens
  came from Windows). The authoritative check is PR #33's CI run going green on
  all three OSes for `test_042`.

## Implementation Steps

1. **`src/segqc/synth/golden.py`** — add `reports_close(a, b, *, rel_tol=1e-9,
   abs_tol=1e-12) -> bool`: recursive; `dict` → same key set, recurse per key;
   `list` → same length, recurse pairwise (order-sensitive); `bool` → exact
   identity (guard *before* the numeric branch, since `bool` is an `int`
   subclass); `int`/`float` → `math.isclose(a, b, rel_tol=rel_tol,
   abs_tol=abs_tol)`; everything else → `==`. Add `math` import and `__all__` +
   `segqc/synth/__init__.py` re-export.
2. **`check_case_golden`** — build the fresh report, `json.loads` the committed
   golden text (unchanged read → still raises `FileNotFoundError` if absent),
   and return `reports_close(fresh_report_dict, committed_dict)` instead of the
   canonical-text byte-equality. (Compare the parsed *report dict*, not the
   canonical text, so tolerance applies to numeric leaves.)
3. **`tests/test_042_golden_determinism.py`** — update `test_ac13` to compare
   `reports_close(json.loads(regenerated_text), json.loads(committed_text))`
   per case rather than raw `read_bytes()` equality. Update the module/AC9/AC13
   docstrings to say "within numeric tolerance (cross-platform)" instead of
   "byte-for-byte". Add focused tests for `reports_close` itself (AC1-AC4). Do
   **not** touch AC4/AC5/AC12's byte-exact assertions.
4. **Docstring/reference updates** — note the cross-platform-tolerance vs
   same-platform-byte-exact split in `golden.py`'s module docstring.

## Testing Strategy

- New direct tests for `reports_close` covering AC1-AC4 (within-tolerance True,
  beyond-tolerance False, string/bool/key/list-length/list-order mismatches
  False, bool-is-not-number).
- AC9 (`check_case_golden`) and AC13 now pass via tolerance — the real
  cross-platform confirmation is the CI matrix run (Windows *and* Linux *and*
  macOS), not a single local run. Locally on Windows the whole suite must stay
  green (regression guard for AC4/AC5/AC12 byte-exactness and everything else).
- AC14 (missing golden → `FileNotFoundError`) and AC15 (mutated `verdict` →
  `False`) must still pass unchanged, proving the tolerance comparator did not
  blunt the harness's ability to catch real differences.

## Dependencies

- **Item 042 (✅, Stage 5)** — the golden harness this fix amends.
- **Item 077 (CI pin)** — sibling fix on `ci/verify-environment-gated-capabilities`;
  fixed the *version-drift* half (items 045/063). This item fixes the
  *cross-platform floating-point* half (item 042) that the pin could not. Both
  are needed before PR #33's baseline `test` job is green on all three OSes.
- **Items 037-039 (✅)** — the perturbation operators whose asymmetric-geometry
  output produces the platform-sensitive floats (context; not modified).

## Decisions & Trade-offs

- **Numeric tolerance over the three rejected alternatives** (round-in-
  `canonical_json`+regenerate goldens; single-platform-only gating;
  leave-broken) — human-decided. Trade-off accepted: the *cross-platform*
  fresh-vs-committed check is now "numerically equal" rather than "byte
  identical", but the stricter same-platform byte-determinism guarantee is
  fully retained by AC4/AC5/AC12, and cross-platform byte-identity of these
  floats was never actually achievable in the first place.
