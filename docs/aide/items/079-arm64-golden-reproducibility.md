# Item 079 — arm64 (Apple Silicon) golden-file reproducibility *(deferred)*

> **Created:** 2026-07-14 · status: **deferred** (not scheduled)
> **Stage:** cross-cutting (Stages 2/3/5/6/8 golden & reference-artifact tests)
> **Discovered by:** item 078 / PR #33's CI matrix

---

## Description

When macOS (`macos-latest`, Apple Silicon / **arm64**) was added to the CI
matrix, six tests failed that pass on both x86_64 platforms (ubuntu +
windows):

- `tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot`
- `tests/test_042_golden_determinism.py::test_ac9_...[mode6_crop_at_border]`
  and `::test_ac13_...` (still fails on arm64 *even with item 078's 1e-9
  numeric tolerance* — the arm64 divergence exceeds it for some values)
- `tests/test_045_reference_artifact.py::test_ac10_regenerating_reproduces_committed_bytes`
- `tests/test_063_reference_intensity.py::test_ac13_default_cohort_geometric_stats_identical_on_off_intensity`
  (delta ~0.6% relative — far beyond ULP) and `::test_ac15_..._byte_identically`

**Root cause.** The committed golden / reference-artifact fixtures encode
floating-point aggregates (spline fits, curvature, EDT depths, percentile
statistics over a cohort) generated on **x86_64** (the maintainer's Windows
machine). Those values are not reproducible on **arm64** — different
BLAS/SIMD/libm implementations round differently — *even at identical
numpy/scipy versions* (item 077's `constraints.txt` pin does not help; item
078's numeric tolerance helps for the smaller x86-vs-x86 deltas but is
insufficient for the larger x86-vs-arm64 ones, and `test_022/045/063` compare
exactly rather than via tolerance).

**Interim decision (item 078 / PR #33).** `macos-latest` was **removed from
the CI matrix** (`.github/workflows/ci.yml`), keeping ubuntu + windows (both
x86_64, both green). This is a documented, deliberate scope limit — not a
silent gap.

## Options for a real fix (to evaluate when scheduled)

1. **Architecture-portable goldens** — regenerate every golden/reference
   fixture with values rounded to a precision below the cross-architecture
   noise floor (in `canonical_json` / the artifact builders), then compare at
   that precision. Makes byte/So-tolerance comparison portable but changes
   every committed fixture and needs a defensible precision choice.
2. **Wide-tolerance conversion of all golden tests** — extend item 078's
   `reports_close` approach to `test_022`/`045`/`063` and widen the tolerance
   enough to absorb arm64 divergence (~1% for some values). Coarse — risks
   masking genuine feature regressions.
3. **Reference-platform gating** — run the golden/byte-identity tests only on
   a single designated architecture, skipping them elsewhere with a clear
   reason. Cheapest; leaves the determinism guarantee arch-specific (already
   effectively the case).

## Dependencies

- **Item 078 (✅)** — relaxed `test_042` to numeric tolerance (fixed the
  x86-vs-x86 half); this item is the arm64 remainder.
- **Item 077** — `constraints.txt` CI pin (fixed the version-drift half).
- **Items 022, 042, 045, 063** — the tests/fixtures involved.

## Decisions & Trade-offs

- **Deferred, not fixed now** — the two x86 platforms give real CI coverage
  today; arm64 golden portability is a distinct, larger effort best done
  deliberately rather than bolted onto the CI-bootstrap PR. Recorded here so
  the limitation is tracked and the CI matrix comment points at it.
