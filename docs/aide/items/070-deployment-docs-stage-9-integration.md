# Item 070 — Deployment docs & Stage 9 integration/acceptance *(completes Stage 9)*

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 9 — Containerisation & XNAT Container Service Command (Phase 2)
> **Queue:** [`../queue/queue-008.md`](../queue/queue-008.md) · Item 070
> **Objectives:** Closes Stage 9 — delivers **G5** (deploy on XNAT: runs as an
> XNAT Container Service command on real session data).
> **Suggested branch:** `aide/070-deployment-docs-stage-9-integration`

---

## Description

Close **Stage 9** by (a) writing the **deployment documentation** an operator
needs to build, install, and run the SegQC container on a real XNAT server, and
(b) adding a **Stage-9 acceptance suite** that ties the already-merged Stage-9
deliverables (items 066–069) into one coherent, testable path and proves the
roadmap's literal Stage-9 acceptance bar holds.

**This is an integration + documentation + acceptance-closure item. It writes NO
new production code and NO new pipeline/container logic.** Every executable piece
Stage 9 needs already exists and is ✅ / merged:

- item 066 — repo-root `Dockerfile`: CPU-only `python:3.11-slim` image, deps
  pinned via `constraints.txt`, bundled default reference artifact; no
  ENTRYPOINT (item 068 layers the entry script on top); default vs.
  `--build-arg INSTALL_RADIOMICS=1` radiomics variant.
- item 067 — repo-root `command.json`: XNAT Container Service command declaring
  the scan/seg (+ optional config/reference) mounts, the `reference-mode` /
  `intensity-mode` boolean inputs, the two report outputs, and the
  `xnat` session wrapper (external/derived inputs + output handlers).
- item 068 — `docker/entrypoint.py`: maps the XNAT mounted-directory convention
  to a single `segqc run` invocation; clean `Error: …` + non-zero exit (never a
  raw traceback) on a missing/empty/ambiguous/non-NIfTI mount, *before* any
  report is written.
- item 069 — `tests/test_069_container_smoke.py` + the shared
  `tests/conftest.py` `requires_docker` marker and session-scoped
  `docker_image_tag` fixture (image tag `segqc:test-066`): Docker-gated
  `docker run` smoke test through the entry script at the exact
  `command.json` mount paths, asserting the produced reports validate against
  the v0 schema; skips cleanly when Docker is absent.

**What it delivers.**

1. **Deployment documentation** at **`docs/deployment.md`** (see Assumptions for
   the location choice) covering the four operator-facing topics the queue item
   names: **(a)** building the image (default + radiomics variant), **(b)**
   installing `command.json` on an XNAT server, *referencing the official XNAT
   Container Service install steps*, **(c)** configuring inputs on a real XNAT
   session (scan resource, segmentation resource, optional config/reference
   overrides, and the reference-/intensity-mode toggles), and **(d)**
   troubleshooting the common failure modes item 068 surfaces.
2. **A Stage-9 acceptance suite** (`tests/test_070_acceptance_stage9.py`, plus an
   optional doc-content sibling) that asserts the roadmap's **literal Stage-9
   acceptance wording** holds, decomposed into its three clauses (see AC8–AC11).
3. **Reconciliation of `docs/aide/progress.md`'s Stage 9 section** — performed by
   the **validator** at merge via the `aide` CLI, **not** by a pytest assertion
   and **not** by this spec's builder/test-writer (see "Progress reconciliation"
   below and the Assumptions). **`roadmap.md` is a PR-gated framework file and is
   NOT edited by this direct-merge item** — mirroring items 049/057/065 exactly.

**Roadmap Stage-9 acceptance wording this item must make provably true**
(`roadmap.md` Stage 9 → *Validation / acceptance*, verbatim):

> **Container runs the pipeline on a mounted case, producing JSON + human report;
> `command.json` validates; install steps documented (G5).**

**What it is NOT.** No change to `Dockerfile`, `command.json`,
`docker/entrypoint.py`, `constraints.txt`, `pyproject.toml`, `src/segqc/**`, or
any existing test. No new fixture, image variant, CLI flag, schema field, or
reference rebuild. No live-XNAT integration (Stage 9 is validated locally per the
queue's "Local-testability note"). No `roadmap.md` edit (PR-gated). No
`progress.md` edit by builder/test-writer (the validator reconciles ✅ via the
CLI).

## Acceptance Criteria

_Each criterion atomic, observable, and directly testable — one test per AC.
AC1–AC6 are doc-presence/content checks (full prose cannot be asserted verbatim,
so each asserts the doc exists and mentions the required topic/command tokens).
AC7–AC11 are the Stage-9 acceptance suite. Progress reconciliation is a
validator action, not an AC — see the note after the list._

- [ ] **AC1: deployment doc exists.** A non-empty Markdown deployment document
  exists at `docs/deployment.md` (readable UTF-8, non-trivial length).

- [ ] **AC2: building-the-image documented.** `docs/deployment.md` documents
  building the image: it contains the default build command
  `docker build -t segqc:latest .` (or an equivalent `docker build … .` shown as
  a command) **and** the radiomics-enabled variant via the
  `INSTALL_RADIOMICS` build arg (the token `INSTALL_RADIOMICS` appears).

- [ ] **AC3: installing `command.json` on XNAT documented, with an official
  reference.** The doc has an install section describing loading/enabling the
  SegQC command on an XNAT server (the tokens `command.json` and `XNAT` appear in
  an install context) **and** links the official XNAT Container Service
  documentation (a `wiki.xnat.org` container-service URL is present).

- [ ] **AC4: configuring inputs on an XNAT session documented.** The doc
  describes configuring a real XNAT session's inputs: it names the scan and
  segmentation resources and the optional config/reference overrides, and
  mentions the `reference` and `intensity` mode toggles (the tokens `scan`,
  `segmentation` (or `seg`), `reference`, and `intensity` all appear in an
  input-configuration context).

- [ ] **AC5: troubleshooting common failure modes documented.** The doc has a
  troubleshooting section covering the item-068 failure modes: a missing/empty
  or ambiguous (multiple-file) input mount and a non-NIfTI input, and states that
  such failures surface as a single `Error:` message with a non-zero exit code
  (not a raw traceback). The tokens `Error:` and `troubleshoot` (or
  `Troubleshooting`) appear.

- [ ] **AC6: mount/output contract documented and consistent with
  `command.json`.** The doc names the container's mount paths `/input/scan`,
  `/input/seg`, and `/output` and the two output report filenames
  `segqc_report.json` and `segqc_report.txt` — matching what `command.json`
  declares.

- [ ] **AC7: Stage-9 acceptance module present & collectable.** A test module
  `tests/test_070_acceptance_stage9.py` exists and is import/collect-clean under
  pytest (this assertion itself requires no Docker).

- [ ] **AC8: clause 1 — container produces JSON + human report.** A Docker-gated
  acceptance test drives the packaged image end-to-end (reusing item 069's smoke
  path / the shared `docker_image_tag` fixture) on a mounted fixture case through
  `docker/entrypoint.py` at the `command.json` mount paths, and asserts the run
  exits `0` and produces **both** `/output/segqc_report.json` **and**
  `/output/segqc_report.txt`. It **skips cleanly** (never fails) when Docker is
  unavailable, via the shared `requires_docker` marker.

- [ ] **AC9: clause 2 — `command.json` validates.** A non-Docker acceptance test
  parses the repo-root `command.json` as valid JSON and asserts it carries the
  XNAT Container-Service required top-level keys (`name`, `image`, `type`,
  `command-line`, `mounts`, `inputs`, `outputs`) and is internally consistent
  (every mount path referenced in `command-line`/`outputs` is a declared
  `mounts[*].path`) — mirroring item 067's structural validation.

- [ ] **AC10: clause 3 — install steps documented (acceptance roll-up).** A
  non-Docker acceptance test asserts `docs/deployment.md` exists and documents
  the install workflow — the build command, `command.json` installation, and
  input configuration — tying the documentation clause into the Stage-9 closure
  (distinct from AC2–AC5, which check individual topics).

- [ ] **AC11: literal Stage-9 wording traceable in the closer.** The acceptance
  module records the roadmap's literal Stage-9 acceptance sentence ("Container
  runs the pipeline on a mounted case, producing JSON + human report;
  `command.json` validates; install steps documented") verbatim in its module
  docstring or a module-level constant, so the three clauses (AC8/AC9/AC10) are
  self-documenting against the roadmap bar; a test asserts that sentence is
  present in the module source.

### Progress reconciliation — validator action, NOT a pytest AC

Closing Stage 9 requires reconciling **`docs/aide/progress.md`** (only), done by
the **validator at merge via `python .aide/scripts/aide.py progress …`**, exactly
as items 049/057/065 handled their stage-closer reconciliation. It is deliberately
**not** an Acceptance Criterion (a test asserting `progress.md` shows ✅ would
deadlock — the validator flips it *after* tests pass). At closure the validator
ensures the Stage 9 section reads complete: the five deliverable bullets
(066–070) ✅, both **Acceptance** checkboxes checked, the **Stage summary** row 9
and the **Objective coverage** G5 row set to ✅. **`roadmap.md` is not touched**
(PR-gated framework file).

## Assumptions  <!-- MANDATORY -->

- **Doc location: `docs/deployment.md`.** The queue item says "`docs/deployment.md`
  or a `docker/README.md` — follow whichever location fits the project's existing
  docs layout." The repo's only existing `docs/` content is the AIDE living-docs
  tree under `docs/aide/`; a top-level `docs/deployment.md` is the most
  discoverable home for operator-facing deployment prose (siblings the future
  human docs and is linked from the repo-root `README.md`), and it is the queue's
  first-named option. AC1/AC6/AC7 pin this path. *If the reviewer prefers the doc
  to live at `docker/README.md` (next to the entry script), that is an acceptable
  equivalent — but then AC1/AC10's path and any `README.md` cross-link must be
  updated to match; call it out rather than shipping the doc at both paths.*

- **The Stage-9 acceptance test reuses item 069's smoke machinery, not a fresh
  copy.** The container-run clause (AC8) imports/reuses the shared
  `tests/conftest.py` `requires_docker` marker and session-scoped
  `docker_image_tag` fixture (tag `segqc:test-066`) and drives the same
  bind-mount contract item 069 uses (`-v <scan>:/input/scan:ro`,
  `-v <seg>:/input/seg:ro`, `-v <out>:/output`, entry argv
  `python /app/docker/entrypoint.py --scan-dir /input/scan --seg-dir /input/seg
  --out-dir /output`). Reusing the session fixture means the whole suite triggers
  **at most one** `docker build`. Interface pinned: the fixture yields a built
  image tag and skips (not fails) when Docker/build is unavailable.

- **Happy-path fixtures already exist.** The acceptance smoke reuses the
  committed corpus fixtures item 069 uses —
  `tests/corpus/fixtures/base_scan.nii.gz` (scan) and
  `tests/corpus/fixtures/clean_control_seg.nii.gz` (segmentation). No new fixture
  is added.

- **Mount/output contract is fixed by `command.json` (item 067) and
  `entrypoint.py` (item 068).** Mount paths `/input/scan`, `/input/seg`,
  `/output`, optional `/input/config`, `/input/reference`; output filenames
  `segqc_report.json` / `segqc_report.txt`; in-image entry path
  `/app/docker/entrypoint.py`; failure convention = single `Error: …` line on
  stderr + non-zero exit, no partial output. The doc and AC5/AC6 describe exactly
  these; if any diverged from the merged artifacts, hand back rather than
  documenting a fiction.

- **`command.json` structural validation mirrors item 067.** AC9 re-uses the
  required-top-level-keys + mount-closure checks item 067 already codifies; the
  merged `command.json` has `type: "docker"`, `image: "segqc:latest"`, and the
  seven required keys, so the check passes against the current file.

- **`docs/deployment.md` is prose, not a byte-reproducible fixture.** It needs no
  `.gitattributes` LF pin (the CLAUDE.md determinism gotcha applies only to
  committed byte-identity fixtures, which this is not).

- **This item writes docs + a test only — no `src/segqc` change.** The builder's
  scope here is `docs/deployment.md` (and, if chosen, a `README.md` cross-link);
  the test-writer's scope is `tests/test_070_acceptance_stage9.py` (+ optional
  `tests/test_070_deployment_docs.py`). No file under `source_dir` is modified.

## Implementation Steps

_Builder scope is documentation (`docs/deployment.md`); the executable Stage-9
artifacts already exist and are not modified. Test module is authored by the
test-writer (see Testing Strategy)._

1. **Write `docs/deployment.md`** with these sections, drawing every concrete
   value from the merged artifacts (do not invent):
   - **Overview / prerequisites** — CPU-only Docker host; the image bundles the
     default reference artifact; no GPU required.
   - **1. Build the image** — `docker build -t segqc:latest .` (default, no
     radiomics), and the radiomics variant
     `docker build -t segqc:radiomics --build-arg INSTALL_RADIOMICS=1 .`
     (verbatim from the `Dockerfile` header). Note the image sets no ENTRYPOINT
     and that `docker run <image> segqc …` invokes the CLI directly.
   - **2. Install `command.json` on an XNAT server** — how an admin uploads /
     enables the SegQC command and its `segqc-session` wrapper via the XNAT
     Container Service admin UI, **linking the official XNAT guidance**
     (`https://wiki.xnat.org/container-service/…`, e.g. the container-build /
     install pages). State that the image referenced by `command.json`
     (`segqc:latest`) must be available to the XNAT host's Docker server.
   - **3. Configure inputs on a session** — the `session` external input; the
     `scan-resource` and `seg-resource` derived inputs (mounted read-only at
     `/input/scan` and `/input/seg`); the optional `config-resource` /
     `reference-resource` overrides (`/input/config`, `/input/reference`); and
     the `reference-mode` / `intensity-mode` boolean toggles and what they enable
     (`segqc run --reference` / `--intensity`). Show where the two output
     resources (`segqc_report.json`, `segqc_report.txt`) are written back
     (`as-a-child-of: session`, label `SEGQC`).
   - **4. Local verification** — the `docker run -v …` invocation item 069's
     smoke test uses, so an operator can prove the path locally before touching
     XNAT (reuses the mount contract above).
   - **5. Troubleshooting** — a table of the item-068 failure modes:
     missing/empty mount, ambiguous (multiple-NIfTI) mount, non-NIfTI input, and
     scan↔seg grid/affine mismatch — each with the symptom (single `Error: …`
     line + non-zero exit, no traceback, no partial report) and the fix.
2. **(Optional) Cross-link** the new doc from the repo-root `README.md`
   deployment/usage section (a single relative link). Keep it a one-line
   addition; skip if it risks touching unrelated README content.
3. **(test-writer, separate)** author `tests/test_070_acceptance_stage9.py`
   (+ optional `tests/test_070_deployment_docs.py`) per Testing Strategy.
4. **(validator, at merge)** reconcile the `docs/aide/progress.md` Stage 9
   section via the `aide` CLI (see the Progress-reconciliation note). Do **not**
   edit `roadmap.md`.

## Testing Strategy

_One focused test per AC, plus adversarial/edge cases. Docker-gated tests skip
cleanly (never fail) when Docker is absent, mirroring item 069 and the shared
`requires_docker` marker. Suggested split (test-writer may host AC1–AC6 in the
acceptance module or a `tests/test_070_deployment_docs.py` sibling):_

- **`tests/test_070_acceptance_stage9.py`** — the Stage-9 closer:
  - AC7: module present & collectable (implicit once the module imports clean).
  - AC8 (Docker-gated, `@requires_docker`): reuse the `docker_image_tag` fixture;
    run the container through `docker/entrypoint.py` at the `command.json` mount
    paths against the committed happy-path fixtures; assert exit `0` and that
    **both** `segqc_report.json` and `segqc_report.txt` land in the output mount.
    Optionally assert the JSON validates against the live v0 schema (as item 069
    does) for a stronger "produces JSON report" check.
  - AC9 (no Docker): parse repo-root `command.json`; assert required top-level
    keys and mount-closure consistency.
  - AC10 (no Docker): assert `docs/deployment.md` exists and mentions the build
    command, `command.json` install, and input configuration.
  - AC11 (no Docker): assert the module source embeds the verbatim roadmap
    Stage-9 acceptance sentence (docstring or constant).
- **Doc-content checks (AC1–AC6, no Docker)** — read `docs/deployment.md` once
  and assert the required token/command presence per AC (case-insensitive where
  sensible): build commands + `INSTALL_RADIOMICS` (AC2); `command.json` + `XNAT`
  + a `wiki.xnat.org` URL (AC3); `scan`/`segmentation`/`reference`/`intensity`
  (AC4); `Error:` + `troubleshoot*` + the missing/ambiguous/non-NIfTI modes
  (AC5); the three mount paths + two report filenames (AC6).
- **Adversarial / edge:**
  - AC8 failure-path sanity (Docker-gated, optional): an empty scan mount exits
    non-zero and leaves **no** `segqc_report.*` in the output dir (guards the
    "no partial output" contract the docs promise) — a thin echo of item 069's
    AC12, kept only if it does not duplicate 069 wholesale.
  - AC9 negative: a synthetic `command.json`-shaped dict missing a declared mount
    referenced in `command-line` is rejected by the closure check (proves the
    check is not vacuously passing).
  - AC6 consistency: assert the mount paths the doc names are exactly the set
    `command.json` declares (fail loudly if the doc drifts from `command.json`).
  - Determinism: the doc-content assertions are pure file reads (no ordering /
    flakiness); the Docker smoke reuses item 069's deterministic fixtures.

## Dependencies

- **Item 066** ✅ — `Dockerfile` (image built by the `docker_image_tag` fixture;
  build commands documented in AC2).
- **Item 067** ✅ — `command.json` (validated by AC9; mount/input/output contract
  documented in AC4/AC6).
- **Item 068** ✅ — `docker/entrypoint.py` (mount→CLI mapping and failure
  convention documented in AC5; exercised by the AC8 smoke).
- **Item 069** ✅ — smoke test + shared `tests/conftest.py` `requires_docker`
  marker and `docker_image_tag` fixture (reused by AC8; provides the happy-path
  fixtures and one-build-per-session behaviour).

All ✅ in `progress.md`. Direct structural precedent for the stage-closer +
progress-reconciliation-without-`roadmap.md` pattern: items 049, 057, 065.

## Decisions & Trade-offs

To be updated during implementation.
