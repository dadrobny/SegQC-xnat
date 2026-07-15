# Item 080 — Docker-gating probe must require a Linux daemon

> **Created:** 2026-07-14 · status tracked via commit history (CI-infra fix)
> **Stage:** cross-cutting (fixes item 069's shared Docker fixture)
> **Discovered by:** PR #33's CI matrix (flaky Windows baseline job)

---

## Description

The baseline `test` job on `windows-latest` intermittently **errored** (not
failed) on all Docker-gated tests (`test_066_dockerfile.py`,
`test_069_container_smoke.py`) with, at setup:

```
docker build failed (AC9):
--- stderr ---
no matching manifest for windows(10.0.26100)/amd64 in the manifest list entries
```

**Root cause.** `tests/conftest.py`'s `_docker_available()` (item 069)
returned `True` whenever the `docker` CLI + daemon merely *responded*
(`docker version` exit 0). But Windows GitHub runners ship Docker in
**Windows-containers mode**, whose daemon cannot build the item-066 Linux
image (`FROM python:3.11-slim`) — the `docker build` fails with a
platform/manifest mismatch. The `docker_image_tag` fixture then treated that
non-zero build as a genuine Dockerfile defect (`pytest.fail`), producing
errors. It was *flaky* because whether a given Windows runner instance had a
running daemon at all (clean skip) versus a running Windows-container daemon
(build error) varied between runs.

**Fix.** `_docker_available()` now requires the daemon's **server OS to be
`linux`** (via `docker version`'s `--format` server-OS query, which prints
`linux` or `windows`), since the
image under test is a Linux image. A Windows-container daemon reports
`windows` and is treated as unavailable → the Docker-gated tests skip cleanly,
which is the intended behaviour (they run for real only in the dedicated Linux
`verify-environment-gated` job and on Linux/Docker-Desktop-Linux-mode dev
hosts). A down/unreachable daemon (`docker version` non-zero) also cleanly
returns `False` as before.

This is a general robustness fix to the fixture, not a CI-only workaround: any
contributor on a Windows-containers Docker setup would have hit the same
spurious failure.

## Verification

- Locally (no Docker): `_docker_available()` returns `False`; the 20
  Docker-gated tests in `test_066`/`test_069` **skip** (confirmed), the rest
  pass.
- CI: the Windows baseline `test` job goes green (Docker-gated tests skip
  instead of erroring); the Linux `verify-environment-gated` job is unaffected
  (`Server.Os == "linux"` there, so the tests still run for real).

## Dependencies

- **Item 069 (✅)** — introduced the shared `_docker_available()` /
  `docker_image_tag` fixture this fix hardens.
- **Items 066, 070** — the other Docker-gated test modules that consume it.

## Decisions & Trade-offs

- **Require `Server.Os == linux` over parsing the specific build error** — the
  server-OS check is a precise, forward-looking gate (it also correctly skips
  before wasting time on a doomed build), whereas string-matching the
  manifest-mismatch message would be brittle across Docker versions.
