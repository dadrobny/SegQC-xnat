# Item 113 — Scope `test-numpy-majors` off environment-gated modules

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 113
> **Objectives:** G7
> **Suggested branch:** `aide/113-scope-numpy-majors`

---

## Description

Restrict the `test-numpy-majors` CI job (`.github/workflows/ci.yml:64-81`,
added by item 095) so it no longer runs the Docker- and PyRadiomics-gated
modules.

The job exists to prove the library stays numpy-major-agnostic, and it does that
by running the **full** suite once per numpy leg (`python -m pytest`, line 81).
On GitHub's `ubuntu-latest` runners — which have a real Docker daemon, unlike
many local dev venvs — the Docker-gated smoke tests
(`tests/test_066_dockerfile.py`, `tests/test_069_container_smoke.py`,
`tests/test_070_acceptance_stage9.py`) therefore attempt a real `docker build`
instead of skipping, and have failed on Docker Hub anonymous-pull
rate-limiting / network flakiness rather than on any numpy incompatibility
(observed: `dial tcp … i/o timeout` against `registry-1.docker.io`, in a run
that otherwise reported 3851 passed).

That is incidental flakiness with **no verification value** for this job's
purpose, and the matrix doubles the exposure — once per numpy leg, on every
push. The dedicated `verify-environment-gated` job (line 90) already owns real
Docker and PyRadiomics verification and must keep doing so.

**In scope.** The selection expression for `test-numpy-majors`, and a comment
in the workflow stating what the job covers and what it deliberately does not.

**Not in scope.** `verify-environment-gated`'s coverage. The main `test` job.
Introducing a pytest marker taxonomy (the repo has no `markers` config today —
see Assumptions). Changing any test.

## Acceptance Criteria

- [ ] **AC1: the Docker modules are deselected.** `test-numpy-majors` does not
  collect `tests/test_066_dockerfile.py`, `tests/test_069_container_smoke.py`
  or `tests/test_070_acceptance_stage9.py`.
- [ ] **AC2: the PyRadiomics-gated tests are deselected.** The tests that
  exercise the real PyRadiomics backend are not collected by this job.
- [ ] **AC3: numpy-sensitive coverage is retained.** Every module exercising
  array computation — features, heuristics, eval, synth, reference, pipeline —
  is still collected by this job; the deselection removes only the
  environment-gated modules.
- [ ] **AC4: the intent is legible in the workflow.** A comment on the job
  states that it proves numpy-major agnosticism, that environment-gated paths
  are owned by `verify-environment-gated`, and why running them here is pure
  incidental risk.
- [ ] **AC5: `verify-environment-gated` is untouched.** Its steps and the set of
  tests it asserts must actually run are unchanged.
- [ ] **AC6: the main `test` job is untouched.** It still runs the full suite on
  both platforms.
- [ ] **AC7: the selection is verifiable locally.** The same expression can be
  run locally with `--collect-only` and the collected counts asserted, so the
  deselection cannot silently drift as modules are added.

## Assumptions

- **`--ignore` over a marker taxonomy** (spec-author default). `pyproject.toml`
  configures only `testpaths` and `addopts` — there is no `markers` section and
  no test carries a marker today. Introducing one would mean touching every
  gated test module, which this item's scope forbids. If a future item adds
  markers for another reason, converting this expression is trivial.
- **The gated module list is enumerable and stable.** The three Docker modules
  are named above; the PyRadiomics-gated tests are identified from the
  environment-gating helper the repo already uses rather than by guessing at
  filenames. If they are scattered across otherwise-numpy-sensitive modules,
  prefer a deselect expression over ignoring a whole module, so AC3 is not
  silently violated.
- **AC7 is enforced by a test, not by a comment.** A local test asserting the
  collected set keeps this from rotting the next time a module is added.

## Implementation Steps

1. Enumerate the environment-gated tests precisely: the three Docker modules,
   plus every test gated on PyRadiomics availability (locate via the gating
   helper, not by filename pattern).
2. Choose the narrowest expression that removes exactly those — `--ignore` for
   whole modules, `--deselect` for individual tests inside modules that
   otherwise carry numpy-sensitive coverage.
3. Apply it to the `Test` step of `test-numpy-majors` only.
4. Add the explanatory comment (AC4).
5. Verify locally with `--collect-only` on both the full and the scoped
   expression, and record the two counts.

## Testing Strategy

New module `tests/test_113_ci_numpy_matrix_scope.py` — a workflow-parsing test,
no CI execution required:

- AC1/AC2: parse `.github/workflows/ci.yml`, extract the `test-numpy-majors`
  test command, and assert each gated module/test appears in its exclusion set.
- AC3: assert a representative numpy-sensitive module from each package is
  **not** excluded.
- AC4: assert the job carries a comment naming `verify-environment-gated`.
- AC5/AC6: assert the other two jobs' commands are unchanged from their pinned
  expected form.
- AC7: run `pytest --collect-only` with the scoped expression in a subprocess
  and assert the gated tests are absent and the count is non-trivial.

Adversarial: a renamed gated module (the test should fail loudly, prompting the
expression to be updated); an empty exclusion set; a malformed workflow file.

## Validation

Run the scoped expression locally with `--collect-only`, record the collected
count against the unscoped run, and confirm the difference equals exactly the
gated tests. Confirm on the pull request that `test-numpy-majors` passes on both
legs and that `verify-environment-gated` still runs the real Docker path.

## Dependencies

None.

## Authorised paths

- `.github/workflows/ci.yml`
- `tests/test_113_ci_numpy_matrix_scope.py`
- `docs/aide/items/113-scope-numpy-majors-ci-job.md`

## Environment / Hardware Dependencies

- **Docker** — external tool (not a pip dependency). This item *reduces* where
  Docker is exercised; it must not reduce it to zero. Required fallback:
  `verify-environment-gated` remains the job that installs Docker and fails if
  the gated tests merely skip. The `progress.md` verification row for the Docker
  capability is unaffected by this item and must not be flipped by it.

## Decisions & Trade-offs

- **Expression chosen** (`test-numpy-majors`'s `Test` step, applied verbatim):

  ```
  python -m pytest \
    --ignore=tests/test_066_dockerfile.py \
    --ignore=tests/test_069_container_smoke.py \
    --ignore=tests/test_070_acceptance_stage9.py \
    --deselect tests/test_features_radiomics.py::TestPresentPath
  ```

- **`--ignore` for the Docker modules, `--deselect` for the radiomics class.**
  The three Docker modules are wholly gated by `@requires_docker`
  (`tests/conftest.py`) or are pure text/JSON assertions with no array
  computation — none of them exercises numpy, so a whole-module `--ignore`
  does not violate AC3, and it is the narrowest expression that fully removes
  them (`test_070_acceptance_stage9.py` has 14 non-Docker-gated tests, but
  they are Dockerfile/manifest content assertions, not numpy-sensitive
  coverage). `tests/test_features_radiomics.py`, by contrast, is mostly
  numpy-sensitive builtin-backend coverage (the torch-free first-order
  fallback) that must stay collected per AC3 — only its
  `TestPresentPath` class (autouse `pytest.importorskip("radiomics")`
  fixture) exercises the real PyRadiomics backend, so that class alone is
  `--deselect`ed rather than ignoring the whole module.
- **`--ignore`/`--deselect` over a pytest marker taxonomy.** Per the
  Assumptions: no `markers` section exists in `pyproject.toml` today, and
  adding one would require touching every gated test module, which is out of
  this item's authorised paths (`.github/workflows/ci.yml`, this spec, and
  the test file only).
- **Measured collection counts** (this machine, full dev venv incl.
  PyRadiomics installed): unscoped `--collect-only` collects **5016** tests;
  the scoped expression collects **4945** selected + 5 deselected (4950
  addressed), a removal of **71** tests overall — the 3 Docker modules plus
  the 5-test `TestPresentPath` class (68 + 5 lines up cleanly with the
  3-module + 1-class exclusion set; the absolute totals differ slightly from
  a from-clean-checkout run since this venv already carries this item's own
  25-test module, `tests/test_113_ci_numpy_matrix_scope.py`, in its
  collection). AC7's committed test re-derives this delta from the workflow
  file itself (not a hardcoded count) so it cannot silently drift as new
  tests are added elsewhere in the repo.
