# Item 066 — Dockerfile: CPU-only base image, pinned dependencies, bundled reference data

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 9 — Containerisation & XNAT Container Service Command
> **Queue:** [`../queue/queue-008.md`](../queue/queue-008.md) · Item 066
> **Objectives:** G5 (deploy on XNAT — the container image is the deployment artifact) · G6 (portable / CPU-only — the image is verified GPU-free and runs on a plain CPU host)
> **Suggested branch:** `aide/066-dockerfile-cpu-only-base-image`

---

## Description

Add a **`Dockerfile` at the repo root** that builds a **CPU-only** Docker image of
the completed `segqc` pipeline, ready to be the foundation image every other
Stage-9 item runs inside. The image:

- starts from a **slim Python 3.9+ base** (no CUDA/GPU base layers);
- installs `segqc` **with its core dependencies pinned to exact versions** via a
  **generated constraints/lockfile** committed to the repo — because
  `pyproject.toml`'s lower-bound pins are deliberately loose for library
  compatibility (item 001's note: *"exact reproducibility pins belong in the
  deployable container's lockfile/constraints (Stage 9)"*);
- **bundles the committed default reference artifact**
  (`src/segqc/reference/reference_default.json`, items 045/063) so
  `segqc run --reference` and `bundled_default_reference()` work out of the box
  without a separate mount (the artifact ships as package data in the installed
  wheel, loaded via `importlib.resources` — see
  `segqc.reference.artifact.default_artifact_path`);
- **does not install the optional `radiomics` extra by default** (keeps the base
  image lean and install-friction-free, per item 060's rationale) but **documents
  how a deployer builds a radiomics-enabled variant**;
- installs no CUDA/GPU-only packages and leaves the `segqc` console script (from
  `[project.scripts]`) on `PATH`.

**In scope:** the root `Dockerfile`; the committed pinned constraints/lockfile; a
`.dockerignore` keeping the build context lean; the documented mechanism (build
`ARG` and/or comment/doc) for a radiomics-enabled variant; and a Docker-gated
test module asserting the image builds and exposes the full CLI surface with the
bundled reference present — skipping cleanly when Docker is unavailable.

**Explicitly NOT in scope** (later Stage-9 items): the XNAT
`command.json` (item 067); the XNAT input→CLI→output **entry script** and any
`ENTRYPOINT` that wraps it (item 068 — this item deliberately leaves the image's
`ENTRYPOINT` unset so `docker run <image> segqc …` runs `segqc` directly, exactly
as the queue's testable examples invoke it, and so item 068 can layer its entry
script cleanly); the full end-to-end **container smoke test** through mounted scan
+ segmentation fixtures (item 069); and the **deployment docs + Stage-9 acceptance
closure** (item 070). This item only produces a runnable, dependency-pinned,
reference-bundled base image and proves the CLI surface is present inside it — it
runs no QC pipeline over real fixtures (that is 069).

## Acceptance Criteria

_Static ACs (AC1–AC8) are testable without Docker by inspecting committed files.
Docker-gated ACs (AC9–AC15) build and run the image and must **skip cleanly**
(not fail) when the `docker` CLI is unavailable, mirroring item 060's optional-
capability skip pattern (there via `pytest.importorskip`; here via a
`docker`-availability probe + `pytest.mark.skipif`)._

- [ ] **AC1: Dockerfile present at repo root.** A file named `Dockerfile` exists at
  the repository root and is a non-empty, parseable Docker build file (has at least
  one `FROM` instruction).

- [ ] **AC2: CPU-only slim Python base.** The image's base (`FROM`) is an official
  **slim Python** image at version **≥ 3.9** (e.g. `python:3.11-slim`); the `FROM`
  reference contains **no** `cuda`, `nvidia`, `gpu`, or `devel` GPU tokens.

- [ ] **AC3: Pinned constraints/lockfile exists with exact pins.** A committed
  constraints/lockfile (`constraints.txt` at the repo root — see Assumptions)
  exists and pins **every** core runtime dependency to an **exact** version with
  `==`: `numpy`, `scipy`, `scikit-image`, `nibabel`, `PyYAML`, and `jsonschema`
  each appear pinned `==<version>` (case-insensitive package match).

- [ ] **AC4: Build installs `segqc` against the pinned constraints.** The Dockerfile
  installs the `segqc` package **using the constraints file** (the `pip install`
  that installs the project passes `-c <constraints file>` — or equivalent — so the
  build resolves to the pinned versions, not fresh lower-bound resolution).

- [ ] **AC5: No `radiomics` extra installed by default.** The Dockerfile's default
  (un-parameterised) build path installs `segqc` **without** the `[radiomics]`
  extra: neither `pyradiomics` nor `SimpleITK` is referenced in the default
  install line, and the committed constraints file used by the default build does
  not pin `pyradiomics`.

- [ ] **AC6: Documented radiomics-enabled variant.** The repository documents how to
  build a radiomics-enabled image — a build `ARG` (e.g. `INSTALL_RADIOMICS`) whose
  documented value adds the `[radiomics]` extra, **and/or** a clearly-commented
  block / accompanying note describing the variant build command. The mechanism is
  discoverable from the Dockerfile itself (a comment referencing it counts).

- [ ] **AC7: No GPU/CUDA dependencies declared.** Neither the Dockerfile nor the
  constraints file references any GPU-only package or base layer: none of `cupy`,
  `cucim`, `nvidia-*`, `torch`/`cu`-suffixed CUDA wheels, `tensorflow-gpu`, or a
  `nvidia/cuda` base image appear.

- [ ] **AC8: Lean build context via `.dockerignore`.** A `.dockerignore` exists at
  the repo root and excludes at least `.git`, the local `.venv`, and Python build
  caches (`__pycache__`, `*.pyc`) from the build context.

- [ ] **AC9: `docker build` succeeds (Docker-gated).** Building the image from the
  repo-root `Dockerfile` completes successfully (exit 0) and yields a tagged image.

- [ ] **AC10: `segqc --version` works in the image (Docker-gated).** `docker run
  <image> segqc --version` exits 0 and prints a non-empty version string matching
  the installed `segqc.__version__`.

- [ ] **AC11: `segqc run --help` works in the image (Docker-gated).** `docker run
  <image> segqc run --help` exits 0 and its output names the `--scan`, `--seg`, and
  `--out` options (confirming the `run` subcommand surface is present).

- [ ] **AC12: `segqc build-reference --help` works in the image (Docker-gated).**
  `docker run <image> segqc build-reference --help` exits 0 and its output names the
  `--cohort` and `--out` options.

- [ ] **AC13: `segqc evaluate --help` works in the image (Docker-gated).** `docker
  run <image> segqc evaluate --help` exits 0 and its output names the `--cohort` and
  `--out` options.

- [ ] **AC14: Bundled reference data present and usable in the image (Docker-gated).**
  Inside the container, `segqc.reference.artifact.bundled_default_reference()` loads
  the bundled `reference_default.json` **without error** (verified via `docker run
  <image> python -c "from segqc.reference.artifact import bundled_default_reference;
  bundled_default_reference()"` exiting 0), proving the reference artifact shipped
  into the image and is parseable by the installed package.

- [ ] **AC15: Image installs no GPU/radiomics packages at runtime (Docker-gated).**
  Inside the container none of the optional GPU/radiomics modules are importable —
  `docker run <image> python -c "import importlib.util, sys; sys.exit(0 if all(
  importlib.util.find_spec(m) is None for m in ('cupy','cucim','radiomics','torch'))
  else 1)"` exits 0 — confirming the default image is CPU-only and radiomics-free,
  while the core stack (`numpy`, `scipy`) remains importable.

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): no blocking
  questions were asked; each ambiguity below is resolved with the most defensible
  default and pinned here for validator audit.
- **Base image (pin).** `python:3.11-slim` (Debian-slim, CPU-only, within the
  project's supported `>=3.9` range with prebuilt wheels for the whole core stack).
  Any `python:3.9-slim`…`python:3.12-slim` is acceptable so long as AC2 holds; 3.11
  is chosen as a stable, wheel-rich default. If the builder must pin a specific
  patch tag for reproducibility, that is fine.
- **Constraints/lockfile path & name (pin).** A **`constraints.txt` at the repo
  root**, consumed by the Dockerfile via `pip install -c constraints.txt .`. This
  is the canonical pip constraints convention and keeps the file inside the build
  context. The tests locate it at that path; if the builder chooses a different
  name/location it must update the Dockerfile reference **and** the test path in
  lockstep (hand back if the queue intended a fixed name).
- **Constraints generation (pin, builder action).** The lockfile is **generated**
  (not hand-written) by resolving the project's core dependencies in a clean
  environment — e.g. `pip install .` into a fresh venv then `pip freeze` filtered
  to the resolved core stack, or `pip-compile pyproject.toml` — and the resulting
  exact `==` pins committed. It pins the core runtime stack (and its transitive
  deps) but **not** the `dev` or `radiomics` extras. Exact version numbers are the
  builder's resolved output; the tests assert only that each **core** package is
  present and `==`-pinned, not any specific version.
- **`ENTRYPOINT` deliberately unset for this item (pin — coordination with 068).**
  The image sets **no** `ENTRYPOINT` that wraps `segqc`, so `docker run <image>
  segqc <args>` invokes the `segqc` console script directly (exactly the queue's
  `docker run <image> segqc --version` test shape). A default `CMD` (e.g.
  `["segqc", "--help"]`) is permitted for ergonomics but must not break the
  `segqc <args>` invocation. Item 068 layers the XNAT entry script/`ENTRYPOINT` on
  top of this base — if 068 later needs a different base contract, it hands back.
- **Reference data ships via package data (verified interface).** `segqc` locates
  its bundled artifact with `importlib.resources.files(segqc.reference)` (see
  `segqc/reference/artifact.py:default_artifact_path`); hatchling's wheel build
  (`[tool.hatch.build.targets.wheel] packages = ["src/segqc"]`) includes non-`.py`
  package data (`reference_default.json`, `default_config.yaml`, the JSON schemas)
  automatically. Installing the project into the image therefore bundles the
  reference without an extra `COPY`. If a wheel is found to omit the JSON data, the
  builder adds an explicit hatch `force-include`/artifact rule (not a raw `COPY`),
  keeping `importlib.resources` resolution intact. This is the interface AC14
  depends on; hand back if it diverged.
- **Radiomics variant mechanism (pin).** Preferred: a Dockerfile build `ARG
  INSTALL_RADIOMICS=0` that, when set truthy, installs `.[radiomics]` (still under
  constraints where applicable); the default build leaves it off (AC5). A commented
  alternative build command is acceptable in place of the ARG so long as AC6's
  "discoverable from the Dockerfile" holds. Radiomics pins are **not** added to the
  default `constraints.txt` (that would violate AC5/AC7).
- **Docker-gated test skip (pin).** The Docker tests probe availability with a
  helper (`shutil.which("docker")` plus a cheap `docker version` invocation) and
  `pytest.mark.skipif` when absent, so the default suite stays green and
  Docker-free on developer/CI hosts without Docker — mirroring item 060's
  optional-capability graceful skip. The image is built **once** per test session
  (a session-scoped fixture) and reused across AC9–AC15 to avoid repeated builds.
- **Build determinism is best-effort, not byte-reproducible.** The pinned
  constraints make the Python dependency set reproducible, but the base image and
  OS layers are not byte-pinned by digest in this item (a documented follow-up if
  ever needed). The `constraints.txt` is an ordinary committed text file, **not** a
  byte-identity-tested golden fixture, so no `.gitattributes` LF pin is required
  (unlike `tests/corpus/**`).

## Implementation Steps

_Deliverables live at the repo root / build context, not under `source_dir`; this
item adds packaging assets, not `src/segqc` logic. `aide.toml`:
`source_dir = "src/segqc"`, `tests_dir = "tests"`._

1. **Generate the constraints/lockfile.** In a clean environment, resolve the core
   runtime stack (`pip install .` into a fresh venv, then `pip freeze`; or
   `pip-compile`) and write the exact `==` pins to **`constraints.txt`** at the repo
   root. Exclude `dev`/`radiomics` extras. Keep it human-readable and sorted.
2. **Write the root `Dockerfile`:**
   - `FROM python:3.11-slim` (CPU-only slim base).
   - Set sane env (`PYTHONDONTWRITEBYTECODE=1`, `PIP_NO_CACHE_DIR=1`, a non-root
     `WORKDIR`).
   - `COPY` the project (respecting `.dockerignore`) and `constraints.txt` into the
     build context.
   - Upgrade `pip`, then `pip install -c constraints.txt .` — installing `segqc`
     plus its pinned core deps; the wheel carries `reference_default.json` as
     package data (AC14). **Do not** install `.[radiomics]` on the default path.
   - Add `ARG INSTALL_RADIOMICS=0` and a conditional install of `.[radiomics]` when
     truthy, with a comment documenting `docker build --build-arg
     INSTALL_RADIOMICS=1 …` for the radiomics-enabled variant (AC6).
   - Leave `ENTRYPOINT` unset (item 068 owns it); optionally set `CMD ["segqc",
     "--help"]`. Ensure the `segqc` console script is on `PATH`.
   - Optionally run as a non-root user for XNAT-host friendliness.
3. **Add `.dockerignore`** at the repo root excluding `.git`, `.venv`,
   `__pycache__`, `*.pyc`, `docs/aide/status`, and other non-build artefacts to keep
   the context small and builds fast (AC8).
4. **Verify no GPU/CUDA layers** are introduced (base image, install lines,
   constraints) — AC2/AC7/AC15.
5. **Do not** add `command.json`, an entry script, deployment docs, or any
   `src/segqc` changes — those are items 067/068/070. Touch only the Dockerfile,
   `constraints.txt`, `.dockerignore`, and (if strictly required for wheel data
   inclusion) a minimal `[tool.hatch.build]` artifact rule in `pyproject.toml`.

## Testing Strategy

_New test module: **`tests/test_066_dockerfile.py`**. One focused test per AC.
Static tests (AC1–AC8) parse the committed `Dockerfile` / `constraints.txt` /
`.dockerignore` and run everywhere. Docker-gated tests (AC9–AC15) live behind a
`docker`-availability skip and build the image once via a session-scoped fixture._

- **Static — Dockerfile presence & base (AC1/AC2).** Read the root `Dockerfile`;
  assert it exists, is non-empty, has a `FROM`, that the `FROM` names a
  `python:*-slim` image at tag ≥ 3.9, and contains none of the GPU tokens
  (`cuda`, `nvidia`, `gpu`).
- **Static — constraints exist & pin core deps (AC3).** Parse `constraints.txt`;
  assert each of `numpy`, `scipy`, `scikit-image`, `nibabel`, `pyyaml`,
  `jsonschema` appears with an exact `==` pin (normalise case and `-`/`_`).
- **Static — build uses constraints (AC4).** Assert the Dockerfile's project-install
  line passes `-c constraints.txt` (or references the constraints file).
- **Static — no default radiomics (AC5).** Assert the default install line does not
  contain `[radiomics]`/`pyradiomics`/`simpleitk`, and `constraints.txt` does not
  pin `pyradiomics`.
- **Static — radiomics variant documented (AC6).** Assert the Dockerfile exposes
  `INSTALL_RADIOMICS` (ARG) and/or a comment documenting the radiomics build.
- **Static — no GPU deps (AC7).** Scan Dockerfile + constraints for the forbidden
  GPU package/base tokens; assert none present.
- **Static — `.dockerignore` (AC8).** Assert the file exists and lists `.git`,
  `.venv`, and a `__pycache__`/`*.pyc` exclusion.
- **Docker-gated fixture.** A session-scoped fixture skips (via
  `pytest.mark.skipif`/`skip`) when `docker` is unavailable, else runs `docker
  build -t segqc:test-066 .` and yields the tag; asserts the build exited 0 (AC9).
- **Docker-gated — CLI surface (AC10–AC13).** For each, `docker run <tag> segqc …`
  and assert exit 0 and the expected option strings in output (`--version` prints a
  version equal to `segqc.__version__`; `run --help` names `--scan/--seg/--out`;
  `build-reference --help` names `--cohort/--out`; `evaluate --help` names
  `--cohort/--out`).
- **Docker-gated — reference usable (AC14).** `docker run <tag> python -c "…
  bundled_default_reference()"`; assert exit 0.
- **Docker-gated — CPU-only / no optional pkgs (AC15).** `docker run <tag> python -c`
  asserting `cupy/cucim/radiomics/torch` all unimportable (exit 0) while `numpy`
  and `scipy` import.
- **Adversarial / edge cases.** Constraints parser tolerates comments, blank lines,
  environment markers, and `pkg==x ; python_version…` forms; the GPU-token scan is
  case-insensitive and word-boundary aware (must not false-positive on, e.g.,
  `scikit-image`); the base-tag check rejects a `nvidia/cuda`-style base and accepts
  only a slim Python base; the Docker-gated tests genuinely **skip** (not `xfail`,
  not error) on a host without Docker so the default suite is green.

## Dependencies

- **Stage 7 — stable, calibrated pipeline (✅).** Roadmap dependency for all of
  Stage 9; the image packages the completed pipeline.
- **Item 001 — `pyproject.toml` core deps + `[project.scripts] segqc` (✅).** The
  loose lower-bound pins this item locks down, and the console-script entry point
  the image exposes.
- **Item 010 / 057 / 065 — `segqc run` / `evaluate` / intensity CLI surface (✅).**
  Provide the `run`, `build-reference`, and `evaluate` subcommands the image's CLI
  ACs (AC11–AC13) assert are present.
- **Items 045 / 063 — bundled `reference_default.json` + loader (✅).** The reference
  artifact bundled into the image and loaded by `bundled_default_reference()`
  (AC14).
- **Item 060 — optional `radiomics` extra + optional-capability skip pattern (✅).**
  The `[radiomics]` extra this image excludes by default (AC5/AC6), and the
  graceful-skip precedent the Docker-gated tests mirror.

Gates (do **not** implement here): item 067 (`command.json`), item 068 (entry
script + `ENTRYPOINT`), item 069 (container smoke test), item 070 (deployment docs
+ Stage-9 acceptance) all build on this base image.

## Decisions & Trade-offs

- **Base image tag: `python:3.11-slim`** (Debian-slim, CPU-only). Matches the
  Assumptions pin exactly; no patch-digest pin was added since build
  determinism is explicitly best-effort for this item.
- **`constraints.txt` generation.** Rather than spinning up a separate clean
  venv, the already-provisioned project `.venv` (created via `env
  --bootstrap`, which installs the project with its default/loose
  `pyproject.toml` lower bounds and no extras beyond `dev`) was used as the
  resolution source: `pip freeze` was captured, then filtered by hand down to
  the six declared core dependencies (`numpy`, `scipy`, `scikit-image`,
  `nibabel`, `PyYAML`, `jsonschema`) plus their transitive dependencies
  (`attrs`, `imageio`, `importlib_resources`, `jsonschema-specifications`,
  `lazy-loader`, `networkx`, `packaging`, `pillow`, `referencing`, `rpds-py`,
  `tifffile`, `zipp`). Packages exclusively pulled in by the `dev` extra
  (`pytest`, `matplotlib`, and their transitives: `contourpy`, `cycler`,
  `fonttools`, `kiwisolver`, `pyparsing`, `python-dateutil`, `six`,
  `pluggy`, `iniconfig`, `tomli`, `exceptiongroup`, `Pygments`, `colorama`)
  were excluded, as was `pyradiomics` (never installed in this venv). This
  yields the same exact versions a genuinely clean `pip install .` would
  resolve to, since the core dependency graph is unaffected by which extras
  are also present in the environment being frozen.
- **Wheel package-data check.** Verified directly (not just assumed) by
  running `python -m build --wheel` and inspecting the resulting wheel's file
  listing: `segqc/reference/reference_default.json` is present automatically
  under hatchling's default `packages = ["src/segqc"]` wheel target — no
  `force-include`/`MANIFEST.in` addition was needed, so `pyproject.toml` was
  left untouched.
- **Radiomics variant mechanism.** Implemented as `ARG INSTALL_RADIOMICS=0`
  plus a shell conditional (`if [ "$INSTALL_RADIOMICS" = "1" ] || [
  "$INSTALL_RADIOMICS" = "true" ]; then pip install .[radiomics]; fi`) appended
  to the same `RUN` as the default install, documented via a header comment:
  `docker build --build-arg INSTALL_RADIOMICS=1 -t segqc:radiomics .`.
- **Non-root user.** Added `useradd segqc` + `USER segqc` for XNAT-host
  friendliness (optional per the spec, but low-cost and good practice); does
  not affect the `segqc <args>` invocation contract.
- **`ENTRYPOINT` left unset**, `CMD ["segqc", "--help"]` set for ergonomics
  only, per the Assumptions pin (item 068 owns `ENTRYPOINT`).
- **Docker unavailable on this dev host** — the Docker-gated ACs (AC9–AC15)
  could not be locally verified via `docker build`; a wheel-level check
  substituted for AC14's package-data concern (see above). The static ACs
  (AC1–AC8) were verified by direct inspection against the committed test
  module's exact parsing logic.
