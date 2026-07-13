# Item 068 — Entry script: XNAT inputs → `segqc` CLI → output resources

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 9 — Containerisation & XNAT Container Service Command
> **Queue:** [`../queue/queue-008.md`](../queue/queue-008.md) · Item 068
> **Objectives:** G5 (deploy on XNAT — this script is what actually turns XNAT's mounted-directory input/output convention into a `segqc run` invocation inside the container)
> **Suggested branch:** `aide/068-entry-script-xnat-inputs-segqc`

---

## Description

Add the **container entry script** `docker/entrypoint.py` that translates the
XNAT Container Service mounted-directory convention (pinned by item 067's merged
`command.json`) into a single `segqc run` invocation and leaves the two report
files where XNAT collects them as output resources.

The script:

- accepts the exact argument set item 067's `command.json` invokes it with —
  `--scan-dir /input/scan --seg-dir /input/seg --out-dir /output --config-dir
  /input/config --reference-dir /input/reference` plus the rendered
  `#REFERENCE_FLAG#` / `#INTENSITY_FLAG#` toggles (`--reference` / `--intensity`
  or empty);
- **resolves** the single NIfTI (`*.nii` / `*.nii.gz`) file inside `--scan-dir`
  and `--seg-dir`, and the optional single override file inside `--config-dir`
  (`*.yaml` / `*.yml`) and `--reference-dir` (`*.json`);
- **assembles and invokes** `segqc run` with the mapped flags
  (`--scan`, `--seg`, `--out`, and — when the overrides/toggles apply —
  `--config`, `--reference`, `--reference-artifact`, `--intensity`) so the two
  reports land at `/output/segqc_report.json` and `/output/segqc_report.txt`
  (the literal names `segqc.cli._handle_run` writes and item 067's outputs
  declare);
- **fails loudly** on a misconfigured mount — a missing/empty/ambiguous required
  input dir, a non-NIfTI file, or a malformed segmentation exits **non-zero with
  a clear one-line `Error:` message on stderr, never a raw traceback** — so a
  broken XNAT command surfaces the problem instead of silently producing nothing;
- is added to the image by a **`COPY docker/ /app/docker/`** step in the root
  `Dockerfile` (item 066 deliberately left `ENTRYPOINT` unset and copies only
  `src/` + packaging files; item 067's contract pins the in-image script path to
  `/app/docker/entrypoint.py`).

**In scope:** `docker/entrypoint.py`; the one-line `COPY docker/ /app/docker/`
addition to the root `Dockerfile`; and a Docker-free, `tmp_path`-based unit test
module that mocks the mounted-directory structure and exercises input resolution,
flag mapping, output placement, and failure modes directly.

**Explicitly NOT in scope:** any change to `src/segqc` production code or to the
`segqc run` CLI surface (this script only *calls* it); `command.json` (item 067,
already merged — this item implements the contract it pinned, it does not edit
it); the real `docker run` smoke test through mounted fixtures (item 069); and
the deployment docs + Stage-9 acceptance closure (item 070). No live XNAT
instance is contacted. `progress.md` is **not** edited here (the builder sets 🚧,
the validator reconciles ✅).

## Acceptance Criteria

_Every AC is verifiable Docker-free by importing `docker/entrypoint.py` and
driving it against directory structures built under pytest's `tmp_path`. One
focused test per AC. "Non-zero exit" means `main(...)` returns a non-zero int
(and, when the console path is used, the process would exit non-zero); "clear
message" means a human-readable `Error: …` line on stderr that names the
offending mount/file, not a Python traceback._

- [ ] **AC1: Entry script present with a callable `main`.** A Python module
  exists at `docker/entrypoint.py` exposing `main(argv=None) -> int` (usable as
  `python /app/docker/entrypoint.py …` and importable for tests).

- [ ] **AC2: Single scan file resolved from `--scan-dir`.** Given a `--scan-dir`
  containing exactly one NIfTI file (`*.nii` or `*.nii.gz`), the resolver returns
  that file's path and it is placed after `segqc run --scan` in the assembled
  argv.

- [ ] **AC3: Single seg file resolved from `--seg-dir`.** Given a `--seg-dir`
  containing exactly one NIfTI file, the resolver returns that file's path and it
  is placed after `segqc run --seg` in the assembled argv.

- [ ] **AC4: `--out-dir` maps to `segqc run --out`.** The `--out-dir <dir>` value
  is passed verbatim as `segqc run --out <dir>` in the assembled argv.

- [ ] **AC5: Happy path produces both report files.** Given valid `--scan-dir`,
  `--seg-dir`, and a writable `--out-dir`, `main(...)` returns `0` and both
  `<out-dir>/segqc_report.json` and `<out-dir>/segqc_report.txt` exist afterwards.

- [ ] **AC6: Optional config file resolved and mapped when present.** A
  `--config-dir` containing exactly one `*.yaml`/`*.yml` file causes `--config
  <that-file>` to be appended to the `segqc run` argv.

- [ ] **AC7: Config is a no-op when the dir is absent or empty.** When
  `--config-dir` names a non-existent directory, or an existing directory with no
  `*.yaml`/`*.yml` file, no `--config` flag is added (the bundled default config
  is used) and the run still succeeds.

- [ ] **AC8: Optional reference file resolved and mapped when present.** A
  `--reference-dir` containing exactly one `*.json` file causes **both**
  `--reference` and `--reference-artifact <that-file>` to be present in the
  `segqc run` argv.

- [ ] **AC9: Reference override is a no-op when the dir is absent or empty.** When
  `--reference-dir` names a non-existent directory, or an existing directory with
  no `*.json` file, no `--reference-artifact` flag is added.

- [ ] **AC10: `--reference` toggle forwarded verbatim.** When the entry script is
  invoked with `--reference` and no reference-dir file, `--reference` appears in
  the `segqc run` argv and `--reference-artifact` does not.

- [ ] **AC11: `--intensity` toggle forwarded verbatim.** When the entry script is
  invoked with `--intensity`, `--intensity` appears in the `segqc run` argv; when
  it is not, `--intensity` does not appear.

- [ ] **AC12: `--reference` never duplicated.** When invoked with **both** the
  `--reference` toggle and a `--reference-dir` JSON file, `--reference` appears
  in the `segqc run` argv **exactly once** and `--reference-artifact <file>` is
  present.

- [ ] **AC13: Invokes `segqc run` via `segqc.cli.main`.** The entry script runs
  the pipeline by importing and calling `segqc.cli.main(argv)` with the assembled
  argv (documented mechanism — see Assumptions) and returns that call's exit code
  on success.

- [ ] **AC14: Missing scan dir → clear error, non-zero exit.** A `--scan-dir` that
  does not exist causes `main` to return non-zero and print an `Error:` line
  naming the missing scan directory — no traceback, no report written.

- [ ] **AC15: Empty scan dir → clear error, non-zero exit.** A `--scan-dir` that
  exists but contains no NIfTI file causes non-zero exit with a clear message
  naming the empty/no-NIfTI scan directory.

- [ ] **AC16: Ambiguous scan dir → clear error, non-zero exit.** A `--scan-dir`
  containing two or more NIfTI files causes non-zero exit with a clear message
  reporting the ambiguity (naming the candidates), rather than silently picking
  one.

- [ ] **AC17: Missing seg dir → clear error, non-zero exit.** A `--seg-dir` that
  does not exist (or is empty / has no NIfTI) causes non-zero exit with a clear
  message naming the segmentation directory.

- [ ] **AC18: Non-NIfTI file in a required dir → clear error, non-zero exit.** A
  `--scan-dir` (or `--seg-dir`) whose only file is not a NIfTI (e.g. `notes.txt`)
  resolves no scan/seg and causes non-zero exit with a clear message.

- [ ] **AC19: Malformed segmentation → non-zero exit, clear message (no
  traceback).** A `--seg-dir` containing a file with a NIfTI extension but
  unreadable/malformed content causes `main` to return non-zero with a clear
  `Error:` line (propagated from `segqc run`'s `SegQCInputError` handling), not a
  raw traceback.

- [ ] **AC20: Ambiguous optional override dir → clear error, non-zero exit.** A
  `--config-dir` (or `--reference-dir`) containing two or more matching override
  files causes non-zero exit with a clear message reporting the ambiguity (the
  optional resolver refuses to guess), rather than silently picking one.

- [ ] **AC21: No report written on an entry-script input error.** When the entry
  script fails its own input resolution (AC14–AC18, AC20) it exits **before**
  invoking `segqc run`, so no `segqc_report.json` / `segqc_report.txt` is left in
  `--out-dir`.

- [ ] **AC22: Dockerfile copies the script to the pinned path.** The root
  `Dockerfile` contains a `COPY docker/ /app/docker/` step (or an equivalent copy
  of `docker/entrypoint.py`) that places the script at `/app/docker/entrypoint.py`
  — the exact path item 067's `command.json` `command-line` invokes.

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): no blocking
  questions were asked; each ambiguity below is resolved with the most defensible
  default and pinned here for validator audit.

- **Invocation mechanism — programmatic import, not subprocess (decision).** The
  script invokes the pipeline via `from segqc.cli import main as segqc_main;
  return segqc_main(argv)`, **not** by shelling out to the `segqc` console script.
  Rationale: (1) `segqc.cli.main` already returns a clean process exit code and
  already prints clear `Error:` lines (never tracebacks) for input/config errors
  (`segqc.cli._handle_run` catches `SegQCInputError`/`SegQCConfigError` → prints
  `Error: …` → returns `1`), so AC19's "no traceback" comes for free; (2) it makes
  the whole script unit-testable Docker-free and subprocess-free — a test can call
  `entrypoint.main([...])` and assert on the return code and the on-disk reports;
  (3) same interpreter, same installed `segqc` inside the image. **Trade-off:** a
  subprocess would isolate a hard crash (e.g. a C-level segfault in a dependency)
  into a non-zero exit, whereas an in-process crash could propagate; this is
  accepted because the CLI's own error handling already converts the realistic
  failure modes into clean exit codes, and the entry script wraps the call so an
  unexpected exception still becomes a clear `Error:` + non-zero exit rather than a
  traceback. If a builder later needs process isolation, switching to
  `subprocess.run([sys.executable, "-m", "segqc", …])` is a local change that
  keeps every AC.

- **Entry-script path & Dockerfile edit (pin — item 067 contract).** The script
  lives at `docker/entrypoint.py` in the repo and at `/app/docker/entrypoint.py`
  in the image. Item 066's `Dockerfile` (`WORKDIR /app`, copies only `src/` +
  packaging) needs a **`COPY docker/ /app/docker/`** step added (AC22). The
  `Dockerfile` is a Stage-9 packaging asset, **not** a framework/process file
  (those are `CLAUDE.md`, `aide.toml`, `.aide/**`, `vision.md`, `roadmap.md`,
  `.claude/**`), so editing it here is in scope and does **not** require a
  hand-back.

- **Entry-script argument surface (pin — matches `command.json` command-line).**
  The script's own arg parser accepts: `--scan-dir` (required), `--seg-dir`
  (required), `--out-dir` (required), `--config-dir` (optional), `--reference-dir`
  (optional), `--reference` (`store_true`), `--intensity` (`store_true`). These
  are the arguments item 067's `command-line` passes (the `#…_FLAG#` tokens render
  to `--reference` / `--intensity` or empty). Extra/unknown args are a usage error.

- **NIfTI recognition (pin).** A "NIfTI file" is one whose name ends in `.nii` or
  `.nii.gz` (case-insensitive), matching the extensions `segqc.io.load_volume`
  documents. Resolution scans the **top level** of the mount directory only
  (non-recursive) for determinism; if XNAT is found to nest resource files in a
  subdirectory at deployment (item 070), the builder hands back to widen this.

- **Required-input resolver semantics (pin).** For `--scan-dir` / `--seg-dir`:
  a non-existent dir, an existing dir with **zero** matching NIfTI files, a dir
  whose only files are non-NIfTI, or a dir with **two or more** NIfTI files each
  raise a clear entry-script error (AC14–AC18). Exactly one match is required.

- **Optional-override resolver semantics (pin).** For `--config-dir`
  (`*.yaml`/`*.yml`) / `--reference-dir` (`*.json`): a **non-existent or empty**
  dir (no matching file) resolves to `None` = no override (a no-op — AC7/AC9),
  because XNAT may simply not mount an optional resource; **two or more** matching
  files raise a clear ambiguity error (AC20). This asymmetry with the required
  resolver is deliberate: optional means "absent is fine, ambiguous is not".

- **`segqc run` argv assembly (pin — the flag-mapping contract from item 067's
  Decisions log).** Given the resolved values the script builds, in order:
  `["run", "--scan", <scan>, "--seg", <seg>, "--out", <out-dir>]`, then appends
  `["--config", <cfg>]` iff a config file resolved; `["--reference"]` iff the
  `--reference` toggle was given **or** a reference file resolved (added at most
  once — AC12); `["--reference-artifact", <ref>]` iff a reference file resolved;
  `["--intensity"]` iff the `--intensity` toggle was given. This matches
  `segqc.cli`'s verified `run` flags (`--scan`, `--seg`, `--out`, `--config`,
  `--reference`, `--reference-artifact`, `--intensity`).

- **Output file names are authoritative from `segqc.cli` (verified interface).**
  `segqc run` writes exactly `<out>/segqc_report.json` and `<out>/segqc_report.txt`
  (`segqc.cli._handle_run`), which are the literal names item 067's `outputs`
  declare on `/output`. The script does not rename or move them — it only passes
  `--out <out-dir>` and lets the CLI write in place. If that CLI contract changes,
  this script, item 067, and item 069 update together.

- **Error channel & exit code (pin).** Entry-script-level errors are raised as a
  dedicated `EntryScriptError`, caught in `main`, printed as `Error: <message>` to
  **stderr**, and returned as exit code `1` — mirroring `segqc.cli`'s own
  `Error:`-to-stderr / return-`1` convention. A successful run returns the exit
  code from `segqc.cli.main` (0 on pass/flag-for-review, 1 on aggregated FAIL or a
  downstream input error). No `sys.exit` is called inside helpers (only the
  `if __name__ == "__main__":` guard raises `SystemExit(main())`) so tests can
  assert on the returned int.

- **Test import of the root-level `docker/entrypoint.py` (pin).** `docker/` is a
  repo-root deployment directory, not part of the installed `segqc` package, so
  the test module loads it via `importlib.util.spec_from_file_location` from the
  repo root rather than a plain `import docker.entrypoint` (avoids adding a stray
  top-level package). No `.gitattributes` LF pin is needed — `entrypoint.py` is
  ordinary source, not a byte-identity golden fixture.

## Implementation Steps

_Deliverables live at the **repo root** (`docker/entrypoint.py`, one line in the
root `Dockerfile`), not under `source_dir` — this is a packaging/deployment asset,
not `src/segqc` logic. `aide.toml`: `source_dir = "src/segqc"`, `tests_dir =
"tests"`._

1. **Create `docker/entrypoint.py`** with:
   - Module docstring stating the XNAT-mount → `segqc run` mapping and pinning the
     in-image path `/app/docker/entrypoint.py`.
   - `class EntryScriptError(Exception)` — a clear, caller-facing error type.
   - `_build_parser() -> argparse.ArgumentParser` declaring `--scan-dir`,
     `--seg-dir`, `--out-dir` (required), `--config-dir`, `--reference-dir`
     (optional), and `--reference` / `--intensity` (`store_true`).
   - `resolve_required_nifti(dir_path, role) -> pathlib.Path` — top-level scan for
     `*.nii`/`*.nii.gz`; raise `EntryScriptError` naming `role` on missing dir /
     zero matches / non-NIfTI-only / ≥2 matches (AC2/AC3, AC14–AC18).
   - `resolve_optional_file(dir_path, patterns, role) -> Optional[pathlib.Path]` —
     return `None` when the dir is absent or has no match; the single match when
     exactly one; raise `EntryScriptError` on ≥2 (AC6–AC9, AC20).
   - `build_run_argv(scan, seg, out_dir, config, reference_file, reference_flag,
     intensity_flag) -> list[str]` — the pure argv assembler from Assumptions
     (AC2–AC4, AC6, AC8, AC10–AC12); keep it side-effect-free so tests can assert
     on the list directly.
   - `main(argv=None) -> int` — parse args; resolve scan/seg (required) and
     config/reference (optional) inside a `try/except EntryScriptError` that prints
     `Error: …` to stderr and returns `1` (AC14–AC21); build the argv; call
     `segqc.cli.main(run_argv)` and return its exit code (AC13); wrap that call so
     an unexpected exception also becomes `Error: …` + non-zero rather than a
     traceback.
   - `if __name__ == "__main__": raise SystemExit(main())`.
2. **Add the Dockerfile COPY step (AC22).** In the root `Dockerfile`, after the
   `src/` copy (or alongside it), add `COPY docker/ /app/docker/` so the script
   lands at `/app/docker/entrypoint.py`. Keep it a plain copy; do **not** set
   `ENTRYPOINT` (item 067 invokes `python /app/docker/entrypoint.py …` explicitly
   via `command-line`). Ensure `.dockerignore` does not exclude `docker/`.
3. **Self-check** that `build_run_argv` output is exactly a valid `segqc run` argv
   (flags match `segqc.cli._build_parser`'s `run` subparser) and that resolution
   happens before any `segqc.cli.main` call (AC21).
4. **Do not** touch `src/segqc`, `command.json`, `progress.md`, or any
   framework/process file. Touch only `docker/entrypoint.py`, the one Dockerfile
   line, and the new test module.

## Testing Strategy

_New test module: **`tests/test_068_entrypoint.py`** — **Docker-free**, mocking the
XNAT mount convention with `tmp_path`. Load `docker/entrypoint.py` via
`importlib.util.spec_from_file_location` (repo root resolved from `__file__`).
Reuse the committed synthetic NIfTI fixtures (`conftest.py`'s
`labelled_blocks_files` / `empty_labelmap_files`, which materialise a valid
scan+seg pair under `tmp_path`) to populate mock `/input/scan` and `/input/seg`
dirs. One focused test per AC._

- **Resolution & argv mapping (AC2–AC4, AC6, AC8, AC10–AC12).** Build mock mount
  dirs under `tmp_path`; call the resolvers and `build_run_argv` directly and
  assert on the returned path / argv list (no pipeline run needed). Cover:
  single-file resolution; `--out-dir` → `--out`; config present → `--config`;
  reference file present → `--reference` + `--reference-artifact`; `--reference`
  toggle alone → `--reference` only; `--intensity` present/absent; both toggle +
  file → single `--reference`.
- **Happy path & output placement (AC5).** Copy a valid scan into a `scan/` dir
  and seg into a `seg/` dir; call `main([...])`; assert return `0` and both
  `segqc_report.json` and `segqc_report.txt` exist in the out dir. Optionally
  spot-check the JSON parses.
- **Invocation mechanism (AC13).** Monkeypatch `segqc.cli.main` to a spy that
  records its `argv` and returns a sentinel code; assert the entry script called
  it with the expected assembled argv and propagated the sentinel exit code.
- **No-op optional dirs (AC7/AC9).** Point `--config-dir`/`--reference-dir` at a
  non-existent path and at an existing empty dir; assert the run still succeeds and
  the corresponding flag is absent from the assembled argv.
- **Failure modes (AC14–AC20).** For each: missing scan dir; empty scan dir
  (exists, no NIfTI); ≥2 NIfTI in scan dir; missing seg dir; a `.txt`-only dir;
  a malformed seg (write a `broken.nii.gz` of non-NIfTI bytes); ≥2 config/reference
  override files. Assert `main(...)` returns non-zero, `capsys` stderr contains a
  clear `Error:` line naming the offending dir/file, and (via `pytest.raises` on
  the traceback surface) that no `Traceback` text is emitted.
- **No report on input error (AC21).** After an AC14–AC18/AC20 failure, assert the
  out dir contains neither report file (resolution failed before `segqc run`).
- **Dockerfile COPY (AC22).** Read the root `Dockerfile` as text; assert it
  contains a `COPY docker/ /app/docker/` step (tolerant of whitespace) so the
  script reaches `/app/docker/entrypoint.py`.
- **Adversarial / edge cases.** Case-insensitive extension match
  (`CASE.NII.GZ` recognised); a `.nii.gz` alongside a hidden/dot file is still
  unambiguous; an out dir that doesn't exist yet is created by `segqc run`
  (`mkdir(parents=True)`); a scan dir that is a *file* rather than a directory
  errors cleanly; `build_run_argv` is deterministic (same inputs → identical
  list) and never emits `--reference` twice.

## Dependencies

- **Item 066 — Dockerfile / image (✅, merged).** Provides the base image, the
  `WORKDIR /app`, the deliberately-unset `ENTRYPOINT`, and the `Dockerfile` this
  item adds the `COPY docker/ /app/docker/` line to (AC22).
- **Item 067 — `command.json` (✅, merged).** Pins the mount/argument contract this
  script implements: the mount paths (`/input/scan`, `/input/seg`, `/output`,
  `/input/config`, `/input/reference`), the invocation `python
  /app/docker/entrypoint.py --scan-dir … --seg-dir … --out-dir … --config-dir …
  --reference-dir … #REFERENCE_FLAG# #INTENSITY_FLAG#`, the `--config` /
  `--reference --reference-artifact` file-override mapping, and the
  `segqc_report.json` / `segqc_report.txt` output names.
- **Item 010 / 065 — `segqc run` CLI surface (✅).** Provides the verified `run`
  flags (`--scan`, `--seg`, `--out`, `--config`, `--reference`,
  `--reference-artifact`, `--intensity`), the `segqc.cli.main(argv) -> int`
  entry point this script calls (AC13), and its `Error:`-to-stderr / return-`1`
  error convention reused for AC19.
- **Item 003 — `segqc.io` (✅).** `SegQCInputError` and `load_case`'s
  clear-message-on-malformed-input behaviour underpin AC19's no-traceback exit.

**Gates (do not implement here):** item 069 (real `docker run` smoke test through
these mounts) and item 070 (deployment docs + Stage-9 acceptance closure) build on
this script.

## Decisions & Trade-offs

To be updated during implementation.
