# Item 067 — XNAT Container Service `command.json`

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 9 — Containerisation & XNAT Container Service Command
> **Queue:** [`../queue/queue-008.md`](../queue/queue-008.md) · Item 067
> **Objectives:** G5 (deploy on XNAT — this file is the installable command that wires the container into an XNAT Container Service)
> **Suggested branch:** `aide/067-xnat-container-service-command-json`

---

## Description

Add a **`command.json` at the repository root** declaring an **XNAT Container
Service command** for the item-066 image, per
[XNAT's container-build guidance](https://wiki.xnat.org/container-service/building-docker-images-for-container-service).
The command:

- references the **item-066 Docker image** (`segqc:latest` — the tag item 066
  documents `docker build -t segqc:latest .`);
- declares **mounts** for the scan resource, the segmentation resource, and a
  writable output location, plus optional read-only mounts for a config and a
  reference-artifact override;
- declares a **`command-line`** that invokes the item-068 entry script at a
  **fixed, documented path** (`/app/docker/entrypoint.py`), passing the mount
  directories and the reference/intensity toggle flags;
- declares **command inputs** (`reference-mode`, `intensity-mode`) that render
  the `segqc run --reference` / `--intensity` flags, and documents how the
  optional config / reference-artifact mounts map onto `segqc run --config` /
  `--reference-artifact`;
- declares **outputs** for the two report files `segqc run` writes
  (`segqc_report.json`, `segqc_report.txt`, confirmed in `segqc.cli._handle_run`)
  on the writable mount;
- declares an **`xnat` wrapper** (external/derived inputs + output-handlers) so
  the command is actually installable on an XNAT server — mapping a session's
  scan + segmentation resources to the input mounts and the report files back to
  an XNAT output resource.

This item **fixes the mount/argument contract** that item 068's entry script MUST
implement (the two are parallelisable per the queue's sequencing note — they
coordinate only through this documented contract, pinned in **Assumptions**).

**In scope:** the root `command.json`; the documented input→CLI-flag mapping; the
mount/entry-script contract for item 068; and a **pure-JSON / structural** test
module that validates the file with **no Docker and no live XNAT** — it runs in
the default fast suite (unlike items 066/069's Docker-gated tests).

**Explicitly NOT in scope:** the entry script itself and any Dockerfile change to
`COPY` it into the image (item 068 — this item only *pins the path/args* the
script must honour); the actual `docker run` / container smoke test through
mounted fixtures (item 069); and the deployment docs + Stage-9 acceptance closure
(item 070). No `src/segqc` production code is touched. No live XNAT instance is
contacted — validation is structural only.

## Acceptance Criteria

_Every AC below is verifiable by parsing the committed `command.json` as JSON and
inspecting its structure — no Docker, no XNAT server, no `docker run`. One focused
test per AC. Path/name comparisons normalise a leading `/` and trailing `/` and
are exact otherwise._

- [ ] **AC1: `command.json` present and valid JSON.** A file named `command.json`
  exists at the repository root, is non-empty, and parses with `json.load` into a
  JSON **object** (`dict`).

- [ ] **AC2: Required top-level keys present.** The parsed object contains **all
  seven** XNAT Container-Service required top-level keys: `name`, `image`, `type`,
  `command-line`, `mounts`, `inputs`, `outputs`. `name` is a non-empty string;
  `mounts`, `inputs`, `outputs` are JSON arrays.

- [ ] **AC3: `type` is `docker`.** The top-level `type` equals the string
  `"docker"`.

- [ ] **AC4: Image references the item-066 build tag.** The top-level `image` is a
  non-empty string whose repository component (the part before any `:` tag, and
  after any trailing registry/namespace `/`) is `segqc` — i.e. it names the image
  item 066 builds (default `segqc:latest`), not a placeholder or an unrelated
  image.

- [ ] **AC5: Scan input mount declared read-only at `/input/scan`.** `mounts`
  contains an entry with container `path` `/input/scan` and `writable` false (or
  absent, defaulting false).

- [ ] **AC6: Segmentation input mount declared read-only at `/input/seg`.**
  `mounts` contains an entry with container `path` `/input/seg` and `writable`
  false.

- [ ] **AC7: Writable output mount declared at `/output`.** `mounts` contains
  exactly one entry with container `path` `/output` and `writable` **true**.

- [ ] **AC8: Optional config and reference override mounts declared read-only.**
  `mounts` contains a read-only entry at `/input/config` and a read-only entry at
  `/input/reference` (the optional config-YAML and reference-artifact override
  locations).

- [ ] **AC9: Command-line invokes the item-068 entry script at the pinned path.**
  The `command-line` string invokes `python` on `/app/docker/entrypoint.py` (the
  fixed entry-script path item 068 must place in the image) — i.e. it contains the
  substring `python /app/docker/entrypoint.py`.

- [ ] **AC10: Command-line passes the required mount roots to the entry script.**
  The `command-line` string contains each of the three required container mount
  paths `/input/scan`, `/input/seg`, and `/output`.

- [ ] **AC11: Command-line mount references are all declared (command-line →
  mounts).** Every declared mount `path` that appears in `command-line` is a
  member of `mounts`, and conversely each of `/input/scan`, `/input/seg`,
  `/output`, `/input/config`, `/input/reference` referenced in `command-line`
  resolves to a declared mount — no `command-line` mount path is undeclared.

- [ ] **AC12: Output mount references are all declared (outputs → mounts).** Every
  `outputs[].mount` value names a declared mount `name`.

- [ ] **AC13: No orphan mounts (mounts → usage).** Every declared mount is
  *referenced* at least once — by its `path` appearing in `command-line`, or by
  its `name` appearing in an `outputs[].mount`, or by an `xnat`-wrapper
  derived-input's `provides-files-for-command-mount`. No mount is declared and
  never used.

- [ ] **AC14: JSON report output declared.** `outputs` contains an entry whose
  `mount` is the writable output mount and whose `path`/`glob` targets
  `segqc_report.json` (the JSON report file `segqc run` writes).

- [ ] **AC15: Human report output declared.** `outputs` contains a **separate**
  entry whose `mount` is the writable output mount and whose `path`/`glob` targets
  `segqc_report.txt` (the human-readable report file `segqc run` writes).

- [ ] **AC16: `reference-mode` input renders `--reference`.** `inputs` contains a
  boolean input named `reference-mode` (or equivalent) whose true rendering is the
  literal `segqc run` flag `--reference` and whose false rendering is empty, wired
  into `command-line` via a `replacement-key` that appears in the `command-line`
  string.

- [ ] **AC17: `intensity-mode` input renders `--intensity`.** `inputs` contains a
  boolean input named `intensity-mode` (or equivalent) whose true rendering is the
  literal `segqc run` flag `--intensity` and whose false rendering is empty, wired
  into `command-line` via a `replacement-key` that appears in the `command-line`
  string.

- [ ] **AC18: File-override → CLI-flag mapping documented.** The `config` override
  declaration (the `/input/config` mount entry or a co-located input) names the
  `segqc run` flag it maps to — the literal string `--config` appears in its
  `description`/definition — and the `reference` override declaration
  (`/input/reference`) names `--reference-artifact`. (These file overrides flow
  through the entry script per the item-068 contract in Assumptions.)

- [ ] **AC19: XNAT wrapper establishes a session/scan context.** The top-level
  object contains an `xnat` array with ≥1 wrapper object declaring an
  `external-inputs` entry whose `type` establishes the session (or scan) context
  the command runs against.

- [ ] **AC20: Wrapper provides files for the scan and seg mounts.** The `xnat`
  wrapper declares derived-inputs (resources) that each set
  `provides-files-for-command-mount` to the declared scan mount **and** the
  declared segmentation mount respectively (so XNAT populates `/input/scan` and
  `/input/seg`).

- [ ] **AC21: Wrapper declares output-handlers for both reports.** The `xnat`
  wrapper declares `output-handlers` that accept both the JSON-report output
  (AC14) and the human-report output (AC15) and create XNAT output resource(s) on
  the session/scan (each handler's `accepts-command-output` names a declared
  command output).

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): no blocking
  questions were asked; each ambiguity below is resolved with the most defensible
  default and pinned here for validator audit.

- **File location & name (pin).** The command is a single **`command.json` at the
  repository root** (the queue allows `command.json` *or* `xnat/command.json`; root
  is chosen for discoverability, to sit beside the root `Dockerfile`, and for a
  simple test path). If the builder relocates it, the Dockerfile `LABEL
  org.nrg.commands` / install docs (item 070) and the test path must move in
  lockstep.

- **Image reference (pin).** `image = "segqc:latest"`, matching item 066's
  documented default build tag (`docker build -t segqc:latest .`). Deployers retag
  to their registry (`<registry>/segqc:<version>`) at install time; AC4 only
  asserts the repository component is `segqc`, so a retag does not break the test.

- **Entry-script path & invocation (pin — coordination contract with item 068).**
  The entry script lives at **`/app/docker/entrypoint.py`** in the image and is
  invoked **`python /app/docker/entrypoint.py …`**. Item 066's `WORKDIR` is `/app`
  and it copies only `src/` + packaging files, so **item 068 must add a
  `COPY docker/ /app/docker/` (or copy `docker/entrypoint.py` to that path) to the
  Dockerfile** so the script exists at the pinned path. Item 066 deliberately left
  `ENTRYPOINT` unset for exactly this layering; if item 068 needs a different path
  it hands back and this file is updated in lockstep.

- **Mount/argument contract for item 068 (pin).** `command.json` invokes the entry
  script with this fixed, stable interface, which item 068's script MUST honour:
  - **Container mount paths (fixed):** scan resource → `/input/scan` (ro);
    segmentation resource → `/input/seg` (ro); output → `/output` (writable);
    optional config override → `/input/config` (ro, may be empty); optional
    reference-artifact override → `/input/reference` (ro, may be empty).
  - **`command-line` (pinned form):**
    `python /app/docker/entrypoint.py --scan-dir /input/scan --seg-dir /input/seg
    --out-dir /output --config-dir /input/config --reference-dir /input/reference
    #REFERENCE_FLAG# #INTENSITY_FLAG#`
    where `#REFERENCE_FLAG#`/`#INTENSITY_FLAG#` are the replacement keys of the
    `reference-mode`/`intensity-mode` boolean inputs (rendering `--reference` /
    `--intensity` or empty).
  - **Entry-script → `segqc run` mapping (item 068 implements):** resolve the
    single NIfTI (`*.nii`/`*.nii.gz`) in `--scan-dir` → `segqc run --scan <file>`;
    likewise `--seg-dir` → `--seg <file>`; `--out-dir` → `--out <dir>` (reports
    land as `<dir>/segqc_report.json` + `<dir>/segqc_report.txt`); if `--config-dir`
    contains a `*.yaml`/`*.yml` → append `--config <file>` (else use the bundled
    default); if `--reference-dir` contains a `*.json` → append `--reference
    --reference-artifact <file>`; forward `--reference` / `--intensity` verbatim.
    A missing/empty required scan or seg mount → a clear error + non-zero exit
    (item 068's own failure-mode AC), never a raw traceback.

- **Config/reference overrides are file mounts, not scalar string inputs (pin).**
  The config YAML and reference-artifact JSON arrive as **optional resource
  mounts** (`/input/config`, `/input/reference`) whose files the entry script
  resolves — rather than as XNAT scalar string inputs holding container paths.
  This keeps `command.json` static and pushes file resolution into the testable
  item-068 script. The CLI-flag mapping (`--config`, `--reference-artifact`) is
  therefore documented on those mount declarations (AC18), not carried by a
  command `input`. The two **toggles** that take no filesystem value —
  `--reference` (bundled-default reference mode) and `--intensity` — are modelled
  as boolean command `inputs` (AC16/AC17), matching `segqc run`'s `store_true`
  flags.

- **XNAT command schema shape (pin, adaptable).** The file targets XNAT
  Container-Service **`schema-version` `1.0`**. The `xnat` wrapper uses the
  conventional keys (`external-inputs`, `derived-inputs` with
  `provides-files-for-command-mount`, `output-handlers` with
  `accepts-command-output`). Exact XNAT context types (`Session` vs `Scan`) and
  handler resource labels are the builder's defensible choice; if the live XNAT
  schema rejects a key at install time (surfaced by item 070), the builder hands
  back — the tests assert structure/consistency, not a live schema round-trip.

- **Output file names are authoritative from `segqc.cli` (verified interface).**
  `segqc run` writes exactly `segqc_report.json` and `segqc_report.txt` into
  `--out` (`segqc.cli._handle_run`, lines writing `out_path / "segqc_report.json"`
  and `… / "segqc_report.txt"`). The outputs (AC14/AC15) target these literal
  names; if that CLI contract ever changes, this file and item 068 update together.

- **No `.gitattributes` LF pin needed.** `command.json` is an ordinary committed
  config file, **not** a byte-identity-tested golden fixture (unlike
  `tests/corpus/**`), so no `text eol=lf` pin is required (per CLAUDE.md's gotcha,
  that rule applies only to byte-reproducible fixtures).

## Implementation Steps

_Deliverable lives at the **repo root** (`command.json`), not under `source_dir`;
this item adds a packaging/deployment asset, not `src/segqc` logic. `aide.toml`:
`source_dir = "src/segqc"`, `tests_dir = "tests"`._

1. **Author `command.json` at the repo root** with the required top-level keys:
   - `name` `"segqc"`, a `label`/`description`, `version` (may mirror
     `segqc.__version__`), `schema-version` `"1.0"`, `type` `"docker"`, and
     `image` `"segqc:latest"` (AC2–AC4).
   - `mounts`: `scan-in` → `/input/scan` (ro), `seg-in` → `/input/seg` (ro),
     `config-in` → `/input/config` (ro), `reference-in` → `/input/reference` (ro),
     `reports-out` → `/output` (`writable: true`) (AC5–AC8).
   - `command-line`: the pinned form from Assumptions invoking
     `python /app/docker/entrypoint.py` with the mount-dir args + the
     `#REFERENCE_FLAG#`/`#INTENSITY_FLAG#` replacement keys (AC9–AC11).
   - `inputs`: boolean `reference-mode` (replacement-key `#REFERENCE_FLAG#`,
     true-value `--reference`, false-value `""`, default `false`) and boolean
     `intensity-mode` (replacement-key `#INTENSITY_FLAG#`, true-value
     `--intensity`, false-value `""`, default `false`) (AC16/AC17). Name the
     `--config` / `--reference-artifact` mapping in the `config-in`/`reference-in`
     mount descriptions (AC18).
   - `outputs`: `qc-report-json` (mount `reports-out`, path/glob
     `segqc_report.json`) and `qc-report-human` (mount `reports-out`, path/glob
     `segqc_report.txt`) (AC12/AC14/AC15).
2. **Add the `xnat` wrapper** array with one wrapper:
   - `external-inputs`: a session (or scan) context input (AC19).
   - `derived-inputs`: a scan resource `provides-files-for-command-mount:
     "scan-in"` and a segmentation resource `provides-files-for-command-mount:
     "seg-in"`; optional config/reference resources providing `config-in` /
     `reference-in` (AC20; keeps those mounts non-orphan-provisioned).
   - `output-handlers`: handlers whose `accepts-command-output` names
     `qc-report-json` and `qc-report-human`, creating an XNAT output resource
     (e.g. label `SEGQC`) on the session/scan (AC21).
3. **Self-check consistency** before commit: every mount path in `command-line`
   is declared; every `outputs[].mount` and every
   `provides-files-for-command-mount` names a declared mount; no mount is orphaned
   (AC11–AC13).
4. **Do not** add the entry script, edit the Dockerfile, write deployment docs, or
   change `src/segqc` — those are items 068/070. Touch only `command.json` and its
   test module.

## Testing Strategy

_New test module: **`tests/test_067_command_json.py`** — **pure JSON / structural
validation, no Docker and no XNAT**, so it runs in the default fast suite. It
reads the repo-root `command.json` once (module-scoped fixture) via `json.load`
and asserts on the parsed structure. One focused test per AC._

- **Presence & validity (AC1).** Locate `command.json` at the repo root; assert it
  exists, is non-empty, and `json.load`s into a `dict`.
- **Required keys & types (AC2/AC3).** Assert the seven required keys are present
  with the right container types; assert `type == "docker"`.
- **Image (AC4).** Parse `image`, strip any tag/registry, assert repository ==
  `segqc`.
- **Mounts (AC5–AC8).** Index `mounts` by `path`; assert `/input/scan`,
  `/input/seg`, `/input/config`, `/input/reference` present and read-only, and
  `/output` present and `writable: true`.
- **Command-line (AC9–AC11).** Assert the `python /app/docker/entrypoint.py`
  substring; assert `/input/scan`, `/input/seg`, `/output` all appear; scan
  `command-line` for any `/input/…` or `/output` token and assert each is a
  declared mount path (command-line → mounts closure).
- **Output/mount consistency (AC12/AC13).** Assert every `outputs[].mount` is a
  declared mount name; build the set of *used* mounts (command-line paths ∪ output
  mounts ∪ wrapper `provides-files-for-command-mount`) and assert it covers **all**
  declared mounts (no orphan).
- **Outputs (AC14/AC15).** Assert one output targets `segqc_report.json` and a
  distinct output targets `segqc_report.txt`, both on the writable mount.
- **Toggle inputs (AC16/AC17).** Assert the `reference-mode`/`intensity-mode`
  boolean inputs exist, render `--reference`/`--intensity` on true (empty on
  false), and that their `replacement-key`s appear verbatim in `command-line`.
- **Override mapping (AC18).** Assert `--config` appears in the config override
  declaration and `--reference-artifact` in the reference override declaration.
- **XNAT wrapper (AC19–AC21).** Assert the `xnat` array + wrapper exist; a session
  external-input; derived-inputs whose `provides-files-for-command-mount` cover
  the scan and seg mounts; output-handlers whose `accepts-command-output` cover
  both report outputs.
- **Adversarial / edge cases.** The test tolerates optional/extra top-level keys
  (`label`, `description`, `version`, `schema-version`, `environment-variables`)
  without failing; the mount-path scan normalises trailing slashes and does not
  false-match a substring (e.g. `/input/scan` must not satisfy `/input/scan-x`);
  the image-repository parse handles a registry-prefixed tag
  (`ghcr.io/org/segqc:1.0` → `segqc`); the orphan-mount check fails loudly if a
  future edit adds an undeclared mount reference or an unused mount; and the JSON
  parse asserts a clear failure on malformed JSON rather than a bare exception.

## Dependencies

- **Item 066 — Dockerfile / image (✅, merged).** Provides the `segqc:latest`
  image this command references (AC4), the `WORKDIR /app`, and the deliberately-
  unset `ENTRYPOINT` that lets item 068 layer the entry script at
  `/app/docker/entrypoint.py` (the path this file pins).
- **Item 010 / 065 — `segqc run` CLI surface (✅).** Provides the `--scan`,
  `--seg`, `--out`, `--config`, `--reference`, `--reference-artifact`,
  `--intensity` flags this command maps XNAT inputs onto, and the fixed report
  file names `segqc_report.json` / `segqc_report.txt` (AC14/AC15).
- **Stage 7 — stable, calibrated pipeline (✅).** The roadmap dependency for all of
  Stage 9; this command wraps the completed pipeline.

**Parallelisable with (not a hard dependency on):** item 068 (entry script). The
two coordinate only through the pinned mount/argument contract in Assumptions;
item 068 implements that contract and adds the Dockerfile `COPY` for the script.

**Gates (do not implement here):** item 068 (entry script + Dockerfile `COPY`),
item 069 (container smoke test through these mounts), item 070 (deployment docs +
Stage-9 acceptance closure) all build on this command.

## Decisions & Trade-offs

To be updated during implementation.
