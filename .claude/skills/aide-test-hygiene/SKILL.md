---
name: aide-test-hygiene
description: Load before creating or editing a test file — portability rules and tests that can actually fail (conventions §6).
user-invocable: false
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/conftest.py"
  - "**/tests/**/*.py"
---

<!-- reach: test-writer
     Literal, not measured: this body is preloaded into exactly the agent
     specs whose `skills:` frontmatter names `aide-test-hygiene`, at spawn,
     before the role has opened anything — so a repo with no test to read
     still delivers it. The `paths:` above inject nothing on a read (issue
     #85, measured): the description sits in every interactive session's skill
     listing regardless, and the globs only narrow when the runtime
     auto-invokes the skill on its own. `builder` and `validator` open test
     files but write none, and are deliberately not listed.
     `tests/test_structural_budget.py` compares this line to the `skills:`
     lists. -->

<!-- triggers: test-writer
     The interactive half, declared so the glob evaluator stays on an
     assertion path: the roles whose named reads match the `paths:` above.
     Only `test-writer` names a test file (`conftest.py`); the others reach
     `project.tests_dir` without naming a file in it. -->

<!-- pins: .aide/conventions/6-test-hygiene.md
     Quoted from that section; `test_rule_pins.py` fails if either copy moves
     alone.
     - in one place, on one platform, against one checkout, so a defect
       invisible under those conditions is invisible to the entire loop
     - A test must be deterministic and pass on Windows, macOS and Linux, with
       no network access
     - Never write the repo's own working-directory path literally into a test
     - the one rule here a script can decide
     - Any `Path` entering a hash, comparison, or match must be `.as_posix()`
     - an identical tree hashes differently on Windows
     - A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin
     - Treat a warning as authoritative and its silence as partial
     - Prefer calling the function over shelling out to the command that calls
       it
     - Assert a derived value is recognisable *before* asserting anything about
       it
-->

# Test hygiene

`.aide/conventions.md` §6 is the source of truth, including the defect each rule
was earned by. This file is how §6 reaches a role about to write a test: it is
preloaded into `test-writer` at spawn, so it is in that context before the
first test is opened or created, and an interactive session sees
its description in the skill listing, with the `paths:` above keeping the
runtime's own invocation of it to work on a test file. It is **delivery, not a
second source of truth**.

The globs match by filename rather than by `project.tests_dir`, so they hold
whatever a consumer configured: the default pytest naming plus any
directory named `tests`. A project that overrides pytest's `python_files`, or
keeps tests in `spec/`, needs the globs widened to match.

**The gap these close.** Every gate in this loop runs in one place, on one
platform, against one checkout, so a defect invisible under those conditions is
invisible to the entire loop. Each rule below is a class that reached `main`
regardless.

- **A test must be deterministic and pass on Windows, macOS and Linux, with no
  network access.** The rules below are the specific ways that is lost, and
  this general statement binds a case none of them names.
- **Never write the repo's own working-directory path literally into a test.**
  Resolve from the test file: `Path(__file__).resolve().parents[N]`. `aide
  check` warns on this — the one rule here a script can decide.
- **Any `Path` entering a hash, comparison, or match must be `.as_posix()`.**
  `str(Path)` renders the OS-native separator — including a `Path` interpolated
  into an f-string, which calls `str()` — so an identical tree hashes
  differently on Windows.
- **A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin**,
  or `core.autocrlf` rewrites it on checkout and every byte comparison fails on
  Windows only. `aide check` warns on the cases it can decide. Treat a warning
  as authoritative and its silence as partial.
- **Prefer calling the function over shelling out to the command that calls
  it.** The CLI's logic is importable and returns structured data; a subprocess
  boundary adds stdout encoding, platform quirks, and a re-parse of what was
  structured a moment earlier.
- **Assert a derived value is recognisable *before* asserting anything about
  it.** A glob that matched nothing, a capture that came back empty, a slice
  taken from a failed `find()` — each yields a value that flows into the
  assertion and passes while checking nothing at all. A test that cannot fail is
  worse than no test.
