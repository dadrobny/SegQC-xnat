# Item 069 — Local container smoke test

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 9 — Containerisation & XNAT Container Service Command
> **Queue:** [`../queue/queue-008.md`](../queue/queue-008.md) · Item 069
> **Objectives:** G5 (Deploy on XNAT)
> **Suggested branch:** `aide/069-local-container-smoke-test`

---

## Description

Add a **Docker-gated end-to-end smoke test** that runs the real item-066 image
via `docker run` — through the item-068 entry script, at the exact mount paths
item-067's `command.json` declares — against small **existing** repo fixtures
bind-mounted as the scan + segmentation, and asserts the container produces the
two report resources (`segqc_report.json` + `segqc_report.txt`) in the mounted
output directory, that the JSON validates against the v0 report schema, and that
the entry script's clean non-zero failure path fires through a *real* container
(not just the item-068 unit tests).

This is the first item in the stage that exercises the whole packaged path as a
single unit — image → `command.json` mount convention → entry script → `segqc
run` → collected output resources — exactly as the XNAT Container Service would,
but with `docker run -v` standing in for XNAT's mount machinery, so no live XNAT
server is needed.

**This item is test-centric.** Its deliverable is a new pytest module
(`tests/test_069_container_smoke.py`) plus a small, behaviour-preserving refactor
that promotes the shared Docker-gating helpers and the session-scoped image-build
fixture into `tests/conftest.py` so item 066 and item 069 share **one** image
build per session. There is **no `src/segqc` production-code change** expected;
if the smoke test surfaces a genuine defect in the `Dockerfile`, `command.json`,
or `docker/entrypoint.py`, that is handed back to the corresponding item rather
than patched here.

**In scope:** the smoke-test module; the conftest refactor to share the build
fixture; happy-path, schema-validation, optional-mount, and failure-path
assertions driven through real `docker run` invocations; clean skip when Docker
is absent.

**Out of scope (fence):** any change to `Dockerfile` / `command.json` /
`docker/entrypoint.py` behaviour (those are items 066/067/068); deployment docs
and the Stage-9 acceptance closure (item 070); any live-XNAT interaction; adding
new large binary fixtures (reuse committed ones only); GPU / radiomics paths.

## Acceptance Criteria

_Each criterion is an observable property of the smoke-test module, verified by
inspecting/running it. Docker-gated criteria (AC4–AC12) are asserted only when a
Docker daemon is available and skip cleanly otherwise (AC2)._

- [ ] **AC1: Smoke-test module present & collectable.** A new test module
  `tests/test_069_container_smoke.py` exists and is collected by pytest without
  import/collection error, both with and without Docker available.

- [ ] **AC2: Docker-gating is a clean skip.** Every `docker run`/`docker build`
  dependent test in the module is guarded by a `pytest.mark.skipif` (a genuine
  *skip* condition — not `xfail`, not an unguarded call) keyed on Docker
  availability; when the `docker` CLI/daemon is absent the module's Docker-gated
  tests **skip** (never error, never fail, never xfail). Verifiable structurally
  (the marker is a `skipif` whose condition is a bool) and behaviourally (the
  module collects and skips cleanly on a Docker-less host).

- [ ] **AC3: Item-066 image built/reused once per session.** The smoke test
  obtains the CPU-only item-066 image via a **session-scoped** build fixture that
  builds the image **at most once** per test session and is shared with
  `tests/test_066_dockerfile.py` (i.e. the two modules do not each trigger an
  independent build). The fixture skips (not fails) when Docker is unavailable or
  the build cannot run for environmental reasons, mirroring item 066's
  `docker_image_tag` fixture.

- [ ] **AC4: Happy-path container exits 0.** A `docker run` invoking `python
  /app/docker/entrypoint.py --scan-dir /input/scan --seg-dir /input/seg --out-dir
  /output --config-dir /input/config --reference-dir /input/reference`, with the
  scan and segmentation fixtures bind-mounted read-only at `/input/scan` and
  `/input/seg` and a writable host directory bound at `/output` (exactly the
  mount paths `command.json` declares), exits with return code 0.

- [ ] **AC5: Happy-path produces `segqc_report.json`.** After the AC4 run, a file
  named exactly `segqc_report.json` exists in the host directory bound to
  `/output`.

- [ ] **AC6: Happy-path produces `segqc_report.txt`.** After the AC4 run, a file
  named exactly `segqc_report.txt` exists in the host directory bound to
  `/output`.

- [ ] **AC7: Output JSON validates against the report schema.** The
  `segqc_report.json` produced by the AC4 run, parsed with `json.loads`,
  validates (via `jsonschema.validate`) against the same v0 report schema
  `segqc.report` uses (`src/segqc/report_schema_v0.json`) with no
  `ValidationError`.

- [ ] **AC8: Output JSON has the expected deterministic content.** The parsed
  AC4 report has `schema_version == "0.1"`, a non-empty `case_id`, and a
  `verdict` value that is one of the schema's allowed labels
  (`pass` / `flagged-for-review` / `fail`).

- [ ] **AC9: Optional reference mount smoke.** A `docker run` that additionally
  bind-mounts a directory containing exactly one reference-artifact JSON
  (the committed `src/segqc/reference/reference_default.json`) read-only at
  `/input/reference` and passes the `--reference` toggle exits 0, produces both
  report files, the JSON validates against the schema (AC7), and the parsed
  report contains a `reference_delta` block (evidence the mounted reference was
  resolved and forwarded).

- [ ] **AC10: Failure-path container exits non-zero.** A `docker run` with a
  deliberately broken scan mount (a `/input/scan` directory bound from a host
  directory containing **no** NIfTI file) exits with a **non-zero** return code.

- [ ] **AC11: Failure-path emits a clean error, not a traceback.** The AC10 run's
  stderr contains a single `Error:`-prefixed message and does **not** contain a
  Python `Traceback` (the entry script's clean-error convention, exercised
  through a real container).

- [ ] **AC12: Failure-path leaves no partial output.** After the AC10 run,
  neither `segqc_report.json` nor `segqc_report.txt` exists in the host directory
  bound to `/output` (a broken mount produces no partial report resource).

## Assumptions  <!-- MANDATORY -->

- **Reused fixtures (no new binaries added).** The happy path (AC4–AC8) reuses
  the committed matched pair from `tests/corpus/manifest.json`'s `clean_control`
  case: scan `tests/corpus/fixtures/base_scan.nii.gz` (~8.8 KB) and segmentation
  `tests/corpus/fixtures/clean_control_seg.nii.gz` (~16 KB) — the smallest
  committed scan+seg pair, already exercised end-to-end by the Stage-5 golden
  tests, so `segqc run` on it yields a valid, deterministic v0 report. The
  optional-mount case (AC9) reuses the committed
  `src/segqc/reference/reference_default.json` (item 045/063). Should the
  `base_scan`/`clean_control_seg` pair prove unsuitable for a bare `segqc run`
  (e.g. it needs a flag the smoke path does not pass), fall back to the matched
  intensity pair `tests/corpus/intensity/fixtures/clean_hu_scan.nii.gz` +
  `clean_spine_seg.nii.gz`; record the choice in Decisions.

- **Per-role temp input dirs, not the shared fixture dir.** The entry script
  requires each mount directory to contain **exactly one** NIfTI (item 068);
  `tests/corpus/fixtures/` holds many, so the smoke test stages one temp
  directory per role under `tmp_path` (copying the single chosen fixture into
  each) and bind-mounts those, rather than mounting the shared corpus dir.

- **Image is shared with item 066's build, not rebuilt.** The session-scoped
  build fixture and the `_docker_available`/`requires_docker` helpers are promoted
  into `tests/conftest.py` (from `tests/test_066_dockerfile.py`) so both modules
  consume one build per session. This is a mechanical, behaviour-preserving
  refactor of item-066's committed test (same tag, same build command, same
  skip/fail semantics); if the validator judges editing item 066's module
  out-of-scope, the fallback is a self-contained session-scoped fixture in
  `tests/test_069_container_smoke.py` that builds under the **same** tag so
  Docker's layer cache makes the second build a near-instant no-op. Either way no
  AC depends on the sharing mechanism — only on "built at most once per session
  and shared" (AC3).

- **Output-dir writability under the non-root image user.** The item-066 image
  runs as the non-root `segqc` user, so the container must be able to write
  reports into the bind-mounted `/output`. The smoke test makes the host output
  dir writable to the container — either by creating it world-writable
  (`chmod 0o777`) or by passing `docker run --user` to align the container uid
  with the host — and documents the chosen approach in Decisions. On a
  permission failure that is clearly environmental (not a real defect) the test
  degrades to a skip rather than a hard failure, consistent with AC2/AC3.

- **Read-only input mounts.** `command.json` declares the input mounts
  `writable:false`; the smoke test bind-mounts `/input/scan`, `/input/seg`, and
  `/input/reference` with the `:ro` flag to match that contract, and mounts only
  `/output` read-write.

- **Cross-platform bind-mount paths / CI target.** Bind mounts use absolute
  `str(path)` host paths. The primary CI target is a Linux Docker host; on
  Windows/Docker Desktop the `tmp_path` drive must be shared with Docker Desktop
  for the mount to succeed — where the `docker run` cannot set up its mounts for
  such environmental reasons, the affected test degrades to a skip (AC2 pattern),
  keeping the default suite green on hosts without a usable Docker.

- **Dependencies are implemented and merged.** Items 066 (`Dockerfile` +
  `constraints.txt` + `.dockerignore`), 067 (`command.json`), and 068
  (`docker/entrypoint.py`) are ✅ merged; this spec pins their current contract
  (mount paths `/input/scan|seg|config|reference`, `/output`; entry-script argv;
  output filenames `segqc_report.json`/`segqc_report.txt`). If any diverges, hand
  back to that item rather than adapting the smoke test around a defect.

## Implementation Steps

_This item adds tests only; the "code path" below is the test module + a conftest
refactor. No `src/segqc` change is expected._

1. **Promote shared Docker helpers into `tests/conftest.py`.** Move
   `_docker_available()`, the `requires_docker = pytest.mark.skipif(...)` marker,
   and the session-scoped `docker_image_tag` build fixture out of
   `tests/test_066_dockerfile.py` and into `tests/conftest.py` (unchanged
   semantics: same `segqc:test-066` tag, same `docker build -t <tag> .` at
   `REPO_ROOT`, same skip-on-unavailable / fail-on-genuine-build-defect
   behaviour). Update `test_066_dockerfile.py` to consume them from conftest
   (delete its now-duplicated local definitions; keep its structural
   skip-mechanism test working). Add a small `_docker_run_mounts(...)` helper (in
   conftest or the new module) that wraps
   `docker run --rm -v <scan>:/input/scan:ro -v <seg>:/input/seg:ro -v
   <out>:/output [more mounts] <tag> python /app/docker/entrypoint.py <argv>`.
2. **Create `tests/test_069_container_smoke.py`.** Import the shared
   `requires_docker` marker and `docker_image_tag` fixture. Add module docstring
   noting it is Docker-gated and reuses the item-066 image (AC1–AC3).
3. **Fixture staging helper.** A function-scoped helper that, given `tmp_path`,
   creates `scan/`, `seg/`, and `out/` subdirs, copies the chosen scan and seg
   fixtures (one each) into `scan/` and `seg/`, makes `out/` writable to the
   container user, and returns their paths.
4. **Happy-path test (AC4–AC8).** Build the mount argv against `/input/scan`,
   `/input/seg`, `/output`; run the container through
   `/app/docker/entrypoint.py`; assert exit 0 (AC4), both report files present
   (AC5/AC6), JSON schema-valid via the same schema `segqc.report` loads (AC7),
   and deterministic content (AC8). Load the schema from
   `src/segqc/report_schema_v0.json` (or import `segqc.report._SCHEMA`) so the
   test tracks the real schema.
5. **Optional-reference-mount test (AC9).** Stage a temp `reference/` dir holding
   a copy of `src/segqc/reference/reference_default.json`; add
   `-v <reference>:/input/reference:ro` and the `--reference` toggle; assert exit
   0, both files present, JSON schema-valid, and a `reference_delta` key present.
6. **Failure-path test (AC10–AC12).** Stage a `scan/` dir containing a non-NIfTI
   file (or leave it empty); run the container; assert non-zero exit (AC10),
   stderr contains `Error:` and no `Traceback` (AC11), and no report files landed
   in `out/` (AC12).
7. **Skip-mechanism structural test.** Mirror item 066's
   `test_adv_docker_gated_tests_skip_not_error_or_xfail_when_docker_absent` so the
   gating contract (AC2) is asserted even on a Docker-less host.

## Testing Strategy

_The deliverable IS the test module; the strategy below is how each AC is
realised and kept robust._

- **Module:** `tests/test_069_container_smoke.py`; shared fixtures/helpers in
  `tests/conftest.py`.
- **Docker gating (AC2):** all container tests carry `@requires_docker`
  (`pytest.mark.skipif` on `not _docker_available()`); a Docker-less run collects
  the module and skips the gated tests. One always-on structural test asserts the
  marker is a `skipif` with a bool condition (defends against a regression to
  `xfail` or an unguarded `docker` call).
- **Single build (AC3):** the session-scoped `docker_image_tag` fixture in
  conftest performs one `docker build` per session, shared by
  `test_066_*` and `test_069_*`; the build failing for environmental reasons
  (`OSError`/timeout/no network) is a `pytest.skip`, a genuine Dockerfile defect
  is a `pytest.fail` — same policy as item 066.
- **Real `docker run` with bind mounts:** each container test issues a
  `subprocess.run(["docker","run","--rm", *mount_args, tag, "python",
  "/app/docker/entrypoint.py", *entry_argv], capture_output=True, text=True,
  timeout=...)`; input mounts use `:ro`, `/output` is read-write; paths are
  absolute `str(...)` values from `tmp_path`. A generous per-run timeout (e.g.
  120–300 s) prevents a hung container from stalling CI.
- **Per-AC mapping:** AC4 exit code; AC5/AC6 `Path(out/"segqc_report.json").exists()`
  / `..._report.txt`; AC7 `jsonschema.validate(json.loads(text), schema)`; AC8
  field assertions on the parsed dict; AC9 adds the reference mount + `--reference`
  and asserts `"reference_delta" in report`; AC10 non-zero exit; AC11
  `"Error:" in stderr and "Traceback" not in stderr`; AC12 both report paths
  absent.
- **Adversarial / edge cases:**
  - *No-NIfTI scan mount* (empty dir) and *non-NIfTI file* scan mount both
    drive the AC10–AC12 failure path — assert the clean-error contract fires
    inside the real container, not just in the item-068 unit tests.
  - *No partial output on failure* (AC12) guards against a half-written report.
  - *Schema drift guard* — load the live `report_schema_v0.json` (not a copy) so
    the smoke test fails if the container's report shape and the schema diverge.
  - *Output-permission environmental failure* degrades to a skip, not a spurious
    red, so the default suite stays green on hosts with a restrictive Docker
    setup.
  - *Determinism* — AC8 asserts only stable fields (`schema_version`, presence of
    `case_id`, `verdict` ∈ enum), never volatile content, so the smoke test does
    not become brittle to future rule/threshold tweaks.
- **CPU-only / no network at run time:** the container run needs no GPU and no
  network; only the one-time image build may pull the base layer (already covered
  by item 066's build fixture).

## Dependencies

- **Item 066** ✅ — CPU-only `Dockerfile` (`segqc:test-066` build fixture,
  `constraints.txt`, `.dockerignore`); provides the image and the session-scoped
  build fixture / Docker-gating helpers this item shares and promotes to conftest.
- **Item 067** ✅ — `command.json`; provides the authoritative mount paths
  (`/input/scan|seg|config|reference`, `/output`), the `command-line` template,
  and the declared output resource filenames the smoke test drives.
- **Item 068** ✅ — `docker/entrypoint.py`; the process the smoke test invokes at
  `/app/docker/entrypoint.py`, whose clean non-zero failure contract AC10–AC12
  exercise through a real container.
- Report schema `src/segqc/report_schema_v0.json` and serializer `segqc.report`
  (items 009/056/061) — the schema AC7/AC9 validate against.

## Decisions & Trade-offs

To be updated during implementation.
