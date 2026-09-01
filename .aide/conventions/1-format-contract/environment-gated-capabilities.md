### Environment-gated capabilities (optional, additive)

A capability gated behind an optional package or external tool (a GPU
library, Docker, a large/optional pip extra, ...) must degrade gracefully —
its tests skip cleanly (never fail, never silently pass as if exercised) when
the dependency is absent, mirroring the project's existing optional-extra
pattern. That graceful-fallback bar is enough for a stage to reach ✅ under the
rollup rule above — **but** a skip-clean pytest run is not evidence the
optional path was ever run for real, and nothing else records that gap by
default. Two additive, non-blocking mechanisms close it:

- The item template's optional **Environment / Hardware Dependencies**
  section — filled in by any item introducing such a capability, naming the
  package/tool, its `pyproject`/equivalent declaration, and the required
  fallback behaviour.
- `progress.md`'s optional **Environment-Gated Capability Verification**
  table — one row per capability, starting `❓ Unverified`. A stage-closing
  item's Implementation Steps must add/update the row(s) for any capability
  its stage introduced. The row flips to `✅ Verified (date, host/CI)` only
  when a human or a CI runner that actually has the dependency present has
  run the gated path — never inferred from the stage's own ✅ status.

Both mechanisms are opt-in: a project with no environment-gated capability
omits them entirely.

Two additions make the verification *planned* rather than hoped-for:

- **`[validation]` environment profiles** (`aide.toml`, optional) — named,
  deterministic environment checks: `<name> = "<python expression>"`, true iff
  the environment provides the capability (e.g.
  `gpu = "__import__('torch').cuda.is_available()"`). Evaluated by
  `aide env --profile <name>` (exit 0 iff satisfied) in the project venv.
- **Stage-validation items** — a queue that closes a roadmap stage ends with a
  `Validate stage N` item that replays the stage's use cases end-to-end and
  updates the capability table (✅ Verified where the profile is satisfied,
  else an explicit ❓ Unverified with the reason). Item specs may also carry an
  optional **Validation** section (see the item template) that the validator
  must execute — tests prove the code runs; validation observes that it does
  something meaningful.
