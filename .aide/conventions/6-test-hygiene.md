## 6. Test hygiene (portability, and tests that can actually fail)

Runtime-general, like §3. An adapter **delivers** this section to a role about
to write a test rather than pointing at it: a pointer is followed only if the
role chooses to, and these rules bind whether or not it did.

**Every rule below was earned by a defect that passed every gate this loop runs
and reached `main` anyway.** That is the structural point: spec → tests → build
→ validate → merge all execute in one place, on one platform, against one
checkout, so a defect invisible under those conditions is invisible to the
entire loop, indefinitely. Each was caught by a human reading a CI log, or by a
reviewer outside the loop — never by a gate inside it.

**Portability.**

- **A test must be deterministic and pass on Windows, macOS and Linux, with no
  network access.** The rules below are the specific ways that is lost; this is
  the general statement they serve, and it binds a case none of them names.
- **Never write the repo's own working-directory path literally into a test.**
  Resolve from the test file (`Path(__file__).resolve().parents[N]`). An
  absolute path ignores where the process runs, so it passes on the machine
  that authored it — including a fresh clone in a *different* directory — and
  matches nothing anywhere else. Recorded: a hardcoded sandbox path made a glob
  return nothing on every CI runner, collapsing a digest to SHA-256-of-empty
  input and failing all four legs while every local gate stayed green.
- **Any `Path` entering a hash, comparison, or match must be `.as_posix()`.**
  `str(Path)` — including a `Path` interpolated into an f-string, which calls
  `str()` — renders the OS-native separator, so an identical tree hashes
  differently on Windows. This class alone has caused four separate CI-only
  failures.
- **A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin.**
  Without it `core.autocrlf` rewrites the file on checkout and every byte
  comparison against it fails on Windows only. `aide check` warns on the cases
  it can decide: a path built from literals, compared with `==` or fed to a
  hash, resolving to a file that exists in the checkout and is covered by no
  `eol=lf` pattern. It reports **only what it can resolve** — a fixture reached
  through a `tmp_path`, a function argument, or a constant imported from
  another package is skipped in silence rather than guessed at, because the
  majority of `read_bytes()` calls in a real suite compare two freshly
  generated files to each other and need no pin at all. Treat a warning as
  authoritative and its silence as partial: the pin is still your
  responsibility on a path the check cannot see.

**Tests that can actually fail.**

- **Prefer calling the function over shelling out to the command that calls
  it.** The CLI's logic is importable and returns structured data; a subprocess
  boundary adds stdout encoding, platform quirks, and a re-parse of what was
  structured a moment earlier. Recorded: `capture_output=True, text=True`
  returned `stdout is None` on a Windows runner — documented not to happen —
  and the fix was to delete the boundary, not harden it.
- **Assert a derived value is recognisable *before* asserting anything about
  it.** A glob that matched nothing, a capture that came back empty, a slice
  taken from a failed `find()` — each yields a value that flows into the
  assertion and passes while checking nothing. Had that Windows capture
  returned `""` rather than `None`, the loop over its lines would have iterated
  zero times and the test would have reported PASS having verified nothing.

`aide check` warns when a file under `tests_dir` contains the repository's own
absolute path — the one rule here a script can decide, and the one whose
recorded instance survived every other gate for weeks.

The lints in this section read `tests_dir`, never `docs_dir`, so they do **not**
require the roadmap document set: `aide check` in a repo with no `docs_dir` runs
them, says so in a `notice:`, and exits 0. A repo may adopt these conventions and
the CLI without adopting the loop.
