# Seg-QC-xnat — Work Queue 008

> **Status:** ✅ Completed — superseded by queue-009 (2026-07-13).
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-007.md`](queue-007.md) (items 058–065, Stage 8 — all ✅).

---

## Scope of this queue

Delivers roadmap **Stage 9 — Containerisation & XNAT Container Service Command
(G5)** in full. Stage 9 is the *second* stage of "Phase 2 — Extensions" —
packaging the now-complete, calibrated pipeline (Phase 1, Stages 0–7) plus its
Stage-8 image-feature extensions as a **Docker image with an XNAT Container
Service command**, per
[XNAT's container-build guidance](https://wiki.xnat.org/container-service/building-docker-images-for-container-service).

**This is greenfield deployment work — no prior item touches it.** Everything
Stage 9 packages already exists and stays authoritative: the `segqc` CLI
(`segqc run` / `segqc build-reference` / `segqc evaluate`, `pyproject.toml`'s
`[project.scripts]` entry point), the bundled reference artifact
(`src/segqc/reference/reference_default.json`, item 045/063), and the report
schemas (items 009/056/061). Stage 9 does not add pipeline logic; it wraps the
existing pipeline for unattended execution on an XNAT server.

**Milestone delivered:** a CPU-only Docker image that runs `segqc run` (and
optionally the intensity/reference paths) against a mounted scan + segmentation,
producing the JSON + human report as XNAT-managed output resources; an XNAT
Container Service `command.json` declaring the session/scan/segmentation inputs
and report outputs; an entry script translating XNAT's mounted-input/output
convention into `segqc` CLI invocations; and a local (non-XNAT) container smoke
test + deployment docs proving the whole path works before it is ever installed
on a real XNAT server. On completion, Stage 9's roadmap acceptance criterion
holds: *"Container runs the pipeline on a mounted case, producing JSON + human
report; `command.json` validates; install steps documented (G5)."*

**Prioritisation rationale.** Stage 9's only roadmap dependency is **Stage 7**
("stable, calibrated pipeline"), ✅ since queue-006. It is independent of Stage
10 (GPU) and Stage 11 (extensibility/classification), which are sequenced after.
Packaging now — rather than waiting for Stage 10/11 — delivers **G5** (the
vision's XNAT-deployment objective) as soon as the pipeline it wraps is stable,
and gives the project a real, installable artifact. The queue is scoped to
**exactly Stage 9** and stops at the stage boundary.

**Local-testability note.** None of this queue's items require an actual XNAT
server. `command.json` is validated **structurally** (required XNAT
Container-Service keys, correct input/output declarations) against the XNAT
schema conventions, not by installing it into a live XNAT instance. The
"local container smoke test" (item 070) runs the built image directly via
`docker run` with bind-mounted fixture files (reusing the Stage-0/5 test
fixtures already in the repo) and inspects the output resources on disk —
exactly mimicking what the XNAT Container Service does when it invokes the
entry script, without needing XNAT itself. This keeps the whole stage testable
under `pytest`/CI on a plain Docker-capable host.

### Numbering note — read before picking an item

Items 001–065 are complete (Stages 0–8, all ✅ in `progress.md`). This queue
continues at the next free integer and is strictly monotonic: **066–070**.

**Estimated size:** ~1 week (5 items, well within `loop.queue_cap = 10`). Each
item is independently testable locally: the Dockerfile/dependency-pinning item
asserts a successful `docker build` and `segqc --version`/`segqc run --help`
inside the image; the `command.json` item asserts it structurally validates
against the documented XNAT Container-Service shape; the entry-script item
asserts input-mapping/output-collection logic with unit tests (mocking the
mounted-directory convention, no Docker needed); the smoke-test item asserts an
actual `docker run` against fixture files produces the expected output
resources; the closing item asserts the Stage-9 acceptance criterion
end-to-end and documents install steps.

**Sequencing note.** Critical path: **066** (Dockerfile + pinned dependencies +
bundled reference data) is the foundation image every other item runs inside —
merge first. **067** (`command.json`) and **068** (entry script) both depend on
066 (they need to know the final CLI/image shape) but are otherwise
**parallelisable** — `command.json` only needs to know the entry script's
argument/mount conventions, and the entry script only needs the image to exist,
not the finished `command.json`. **069** (local container smoke test) depends
on **both** 067 and 068 (it exercises the entry script through the same
input/output convention `command.json` declares). **070** (deployment docs +
Stage 9 acceptance) depends on everything and closes Stage 9. Recommended
order: 066 → (067 ‖ 068) → 069 → 070.

### Stage-9 deliverable → item coverage

| Stage-9 deliverable | Delivered by item(s) |
|---|---|
| **Dockerfile** (CPU-only base), pinned deps, bundled/mounted reference data | 066 |
| XNAT Container Service **`command.json`** (inputs: session/scan + segmentation; outputs: report resources) | 067 |
| **Entry script** mapping XNAT inputs → CLI → output resources | 068 |
| **Local container smoke test** + deployment docs | 069 (smoke test), 070 (docs + acceptance closure) |

Every deliverable is realised by ≥1 item. Item 066 is the image foundation;
item 070 closes the stage and records the Stage-9 acceptance evidence.

---

## Work items

### Item 066: Dockerfile — CPU-only base image, pinned dependencies, bundled reference data
Add a `Dockerfile` at the repo root building a CPU-only image from a slim
Python 3.9+ base, installing `segqc` (and its core dependencies from
`pyproject.toml`) with **pinned versions** (a generated lockfile/constraints
file, since `pyproject.toml`'s lower-bound pins are deliberately loose for
library compatibility per item 001's note — Stage 9 is where exact
reproducibility pins belong), and bundling the committed default reference
artifact (`src/segqc/reference/reference_default.json`) into the image so
`segqc run --reference` works out of the box without a separate mount. Do
**not** install the optional `radiomics` extra by default (keep the base image
lean and dependency-friction-free, per item 060's own rationale) — document how
a deployer can build a `radiomics`-enabled variant if wanted. Verify the image
runs fully CPU-only (no CUDA/GPU base layers, no GPU-only dependencies).
*Testable:* `docker build` succeeds; `docker run <image> segqc --version` and
`segqc run --help` succeed; a smoke invocation of `segqc build-reference
--help`/`segqc evaluate --help` inside the container confirms the full CLI
surface is present; confirm the image contains no CUDA/GPU base layers.

### Item 067: XNAT Container Service `command.json`
Add a `command.json` (or `xnat/command.json`) declaring an XNAT Container
Service command per the
[XNAT container-build guidance](https://wiki.xnat.org/container-service/building-docker-images-for-container-service):
inputs mapping a session's scan and segmentation resources to mount points the
entry script (item 068) expects; outputs declaring the JSON + human report as
XNAT output resources attached back to the session; the Docker image reference
(from item 066); and the command-line template invoking the entry script.
Document the required/optional XNAT input types (scan resource, segmentation
resource, optional config/reference overrides) and how they map onto `segqc
run`'s existing CLI flags. *Testable:* a test parses `command.json` as valid
JSON and asserts it has the XNAT Container-Service required top-level keys
(`name`, `image`, `type`, `command-line`, `mounts`, `inputs`, `outputs`) and
that declared inputs/outputs are internally consistent (every mount referenced
in `command-line`/`outputs` is declared in `mounts`); no live XNAT instance is
needed for this validation.

### Item 068: Entry script — XNAT inputs → `segqc` CLI → output resources
Add an entry script (e.g. `docker/entrypoint.py` or `docker/entrypoint.sh`,
whichever fits the project's existing conventions better — prefer Python for
testability, matching the rest of the codebase) that: reads the XNAT-mounted
input directories/files (scan, segmentation, optional config/reference
overrides) per the mount convention `command.json` declares; invokes `segqc
run` (via the installed `segqc` CLI or by importing `segqc.cli.main`
programmatically) with the appropriate flags; and places the resulting JSON +
human report into the mounted output directory so XNAT can collect them as
output resources. Handle the common failure modes cleanly (missing/malformed
mounted inputs → a clear error + non-zero exit, not a raw traceback) so a
misconfigured XNAT command fails loudly rather than silently. *Testable:* unit
tests exercise the entry script's input-resolution and output-placement logic
directly (mocking a mounted directory structure with `tmp_path`, no Docker
required) — happy path produces the expected output files; a missing input
directory or malformed segmentation exits non-zero with a clear message.

### Item 069: Local container smoke test
Add a smoke test that actually builds (or reuses a pre-built) image from item
066 and runs it via `docker run` with bind-mounted **existing repo fixture
files** (reuse Stage-0/5 fixtures already committed — e.g.
`tests/corpus/intensity/fixtures/*` or similar small NIfTI pairs, no new large
binary fixtures needed) standing in for an XNAT-mounted scan + segmentation,
through the item-068 entry script, exactly as `command.json` declares the
mounts. Asserts the container produces the expected JSON + human report output
files in the mounted output directory, and that the JSON validates against the
report schema. Skip cleanly (not fail) when Docker isn't available in the
executing environment (mirroring item 060's `pytest.importorskip`-style
graceful degradation for an optional/environment-dependent capability), so the
default test suite stays fast and doesn't hard-require Docker locally or in
CI unless it's present. *Testable:* `pytest` (Docker-gated, skips cleanly when
absent) drives a real `docker run` against mounted fixtures and asserts on the
produced output files' presence, schema-validity, and (where deterministic)
content.

### Item 070: Deployment docs & Stage 9 integration/acceptance *(completes Stage 9)*
Write deployment documentation (e.g. `docs/deployment.md` or a `docker/README.md`
— follow whichever location fits the project's existing docs layout) covering:
building the image, installing `command.json` on an XNAT server (referencing
the official XNAT Container Service install steps), configuring inputs on a
real XNAT session, and troubleshooting common failure modes. Add a final
Stage-9 acceptance check tying together items 066–069 into one coherent,
documented, testable path, and reconcile `docs/aide/progress.md`'s Stage 9
section (deliverable bullets, acceptance checkboxes, summary status) —
`roadmap.md` itself is a PR-gated framework file and is **not** edited by this
item's direct-merge work (mirror items 049/057/065's precedent exactly).
*Testable:* the acceptance check re-runs item 069's smoke test (or an
equivalent end-to-end invocation) and asserts the roadmap's literal Stage-9
acceptance wording holds: "container runs the pipeline on a mounted case,
producing JSON + human report; `command.json` validates; install steps
documented."

---

## Current state (2026-07-13)

Freshly generated; supersedes [`queue-007.md`](queue-007.md) (Stage 8,
items 058–065, all ✅). This is the **second Phase-2 queue** and opens
**Stage 9 — Containerisation & XNAT Container Service Command** on top of the
complete Phase-1 pipeline and Stage-8 image features. No Stage 9 items claimed
yet. **066** (Dockerfile) is the shared foundation and should merge first;
**067** (`command.json`) and **068** (entry script) are then parallelisable;
**069** (smoke test) depends on both; **070** (docs + acceptance) closes the
stage. This queue is landing via a human-reviewed queue PR (the Phase-2 batch
checkpoint).

## Next Step

Per `CLAUDE.md`: `git fetch --all --prune` and check `aide/*` branches first, then
branch per item (`aide/NNN-short-name`) and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit. Start with **066**. Two ways
to proceed: spec the whole queue now with `/aide-spec-queue 008` in one
interactive sitting, or spec per-item during execution via `/aide-run-queue 008`.
