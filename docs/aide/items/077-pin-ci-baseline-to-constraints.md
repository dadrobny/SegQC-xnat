# Item 077 — Pin CI's baseline `test` job to `constraints.txt`

> **Created:** 2026-07-14 · status tracked via commit history, not `progress.md`
> **Scope:** CI/infrastructure fix — cross-cutting (spans items 042/Stage 5,
> 045/Stage 6, 063/Stage 8), not a single-stage product deliverable. Mirrors
> the earlier framework-verification and CI-setup work in *not* being wired
> into a `progress.md` stage bullet (see `.aide/conventions.md`'s
> "Environment-gated capabilities" precedent for the same reasoning).
> **Suggested branch:** `ci/verify-environment-gated-capabilities` (folded
> into the still-open CI-setup PR rather than its own, since it's a fix to
> that same CI workflow before it ever merged)

---

## Description

The first real CI run (`.github/workflows/ci.yml`'s baseline `test` job,
added this same session) failed identically on all three OSes
(ubuntu/windows/macos-latest) in `tests/test_042_golden_determinism.py`,
`tests/test_045_reference_artifact.py`, and `tests/test_063_reference_intensity.py`
— tests that assert **byte-identity** between a freshly regenerated
golden/reference-artifact file and its committed copy.

**Root cause.** `pyproject.toml`'s core dependencies use deliberately loose
lower bounds (`numpy>=1.21`, `scipy>=1.7`, …) — per item 001's own documented
intent, *"exact reproducibility pins belong in the deployable container's
lockfile/constraints (Stage 9), not in library metadata."* CI's fresh
`pip install -e .[dev]` on Python 3.11 resolved those loose bounds to the
**latest** available versions (`numpy==2.4.6`, `scipy==1.17.1`), which differ
from the versions the committed golden files were actually generated against
(`numpy==2.0.2`, `scipy==1.13.1` — the exact versions already pinned in
`constraints.txt`, item 066's Docker lockfile, and installed in this
project's own dev `.venv`). Newer numpy/scipy releases shift last-digit
floating-point rounding in aggregate statistics (mean/std/percentiles over a
cohort), which is enough to break a raw-byte JSON comparison even though the
values are numerically equivalent to any reasonable tolerance. Confirmed via
CI: `"At index 7539 diff: b'8' != b'5'"` — a single last-digit difference deep
inside a percentile value.

**This was invisible before today** because no CI existed prior to this
session, and this dev environment's `.venv` happens to already match
`constraints.txt`'s pins closely (both were built from the same lower-bound
resolution around the same time) — so the golden-file tests always passed
locally by coincidence of environment, not by a documented, enforced
guarantee.

**Fix (human-confirmed decision):** pin CI's baseline `test` job's install
step to use `constraints.txt` (`pip install -e .[dev] -c constraints.txt`)
rather than `pyproject.toml`'s loose bounds — this is not inventing a new
constraint, it is *finally wiring up* item 001's already-stated design
intent. No test code changes; no relaxation of the byte-identity assertions'
semantics. The rejected alternative (relaxing `test_042`/`045`/`063` to a
numeric-tolerance comparison) was explicitly declined: it would weaken what
these tests were designed to prove, for a problem that a CI install-step
change already solves cleanly.

**Trade-off, recorded explicitly:** CI's baseline job no longer exercises the
"a fresh contributor does `pip install -e .[dev]` with no other setup" path
for these specific reproducibility tests — that path is still exercised by
every *other* test in the suite (only 3 of ~3300 tests assert byte-identity),
just not with a guarantee that golden-file byte-identity holds outside the
pinned environment. This is accepted as correct: byte-identity was always
meant to be scoped to the reproducible/pinned environment (item 001's own
words), not to an arbitrary future numpy/scipy release.

## What it is NOT

- Not a relaxation of `test_042`/`045`/`063`'s assertions — they still assert
  raw byte-identity, unchanged.
- Not a `pyproject.toml` change — the loose lower bounds stay loose (correct
  for library-compatibility purposes); only CI's *install step* changes.
- Not tied to a `progress.md` stage bullet — this is CI/infra hygiene
  spanning three already-✅ stages' golden-file tests, not a new product
  capability. No stage's rollup is affected.

## Fix applied

`.github/workflows/ci.yml`'s `test` job:

```diff
- run: pip install -e .[dev]
+ run: pip install -e .[dev] -c constraints.txt
```

with a comment explaining the rationale and pointing at item 001's original
design intent and this item's number for future readers.

## Verification

Re-running CI after this change must show the baseline `test` job green on
all three OSes (confirming golden-file byte-identity holds again once the
pinned versions are actually installed), with the `verify-environment-gated`
job (Docker + radiomics, items 066–070/076) unaffected (it already installs
separately and was already green).

## Dependencies

- Item 066 (✅) — `constraints.txt` itself.
- Item 001 (✅) — the original design-intent comment in `pyproject.toml` this
  fix finally acts on.
- Items 042 (✅, Stage 5), 045 (✅, Stage 6), 063 (✅, Stage 8) — the
  byte-identity tests this fix makes pass in CI for the first time.

## Decisions & Trade-offs

- **Pin-CI-to-constraints.txt over relaxing test semantics** — human-decided
  (see Description); the numeric-tolerance alternative was considered and
  explicitly rejected as unnecessary and semantically weaker.
- **Not wired into `progress.md`** — cross-cutting CI/infra fix, not a
  product-stage deliverable; mirrors the earlier Environment-Gated Capability
  Verification framework work's precedent of living outside stage tracking.
