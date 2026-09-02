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
     - Any `Path` entering a hash, comparison, or match must be `.as_posix()`
     - an identical tree hashes differently on Windows
     - A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin
     - Treat a warning as authoritative and its silence as partial
     - the lint decides a *read shape*, not whether a file needs a pin
     - The immunity is a property of the reader, not of parsing
     - never write "the eol-pin lint passes" as an acceptance criterion
     - `binary` and `-text` count as pins alongside `eol=lf`
     - A test that captures subprocess output as text must pass
       `encoding="utf-8"`
     - It sees only direct calls: a suite that wraps its subprocess calls in a
       helper shows this lint one call site and hides the rest
     - The codec is the producing side's job too
     - a script that writes non-ASCII to stdout or stderr inherits the console
       codepage on Windows, so it must reconfigure its own streams
     - Prefer calling the function over shelling out to the command that calls
       it
     - a test asserting on `aide check`'s own output should call `run_checks`
       in-process
     - Never pin an exact warning or error count from a module that itself
       trips the lint being counted
     - a measurement that includes the measurer
     - Assert a derived value is recognisable *before* asserting anything about
       it
     - A scope claim about a diff belongs on the branch, not in the suite
     - Deriving the base from `aide scope` is not the repair
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
  check` warns on this.
- **Any `Path` entering a hash, comparison, or match must be `.as_posix()`.**
  `str(Path)` renders the OS-native separator — including a `Path` interpolated
  into an f-string, which calls `str()` — so an identical tree hashes
  differently on Windows.
- **A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin**,
  or `core.autocrlf` rewrites it on checkout and every byte comparison fails on
  Windows only. `aide check` warns on the cases it can decide. Treat a warning
  as authoritative and its silence as partial. The lint decides a *read shape*,
  not whether a file needs a pin: `read_text()` applies universal-newline
  translation, so an artifact read that way and parsed draws no warning whether
  or not it is pinned, while **any** `read_bytes()` on a committed path is
  reported. The immunity is a property of the reader, not of parsing. So never
  write "the eol-pin lint passes" as an acceptance criterion: assert the pin
  itself. `binary` and `-text` count as pins alongside `eol=lf`.
- **A test that captures subprocess output as text must pass
  `encoding="utf-8"`.** `text=True` names no codec, so Python decodes with the
  platform's locale codec — UTF-8 on a Linux runner, cp1252 on a Windows one.
  `aide check` warns on this. It sees only direct calls: a suite that wraps its
  subprocess calls in a helper shows this lint one call site and hides the
  rest. The codec is the producing side's job too: a script that writes
  non-ASCII to stdout or stderr inherits the console codepage on Windows, so it
  must reconfigure its own streams. When the reader and the writer disagree the
  read comes back **`None`** rather than raising — the decode runs in
  `subprocess.run`'s reader thread — so assert the value is there before
  asserting anything about it.
- **Prefer calling the function over shelling out to the command that calls
  it.** The CLI's logic is importable and returns structured data; a subprocess
  boundary adds stdout encoding, platform quirks, and a re-parse of what was
  structured a moment earlier. A test asserting on `aide check`'s own output
  should call `run_checks` in-process, which returns `(errors, warnings)` as
  structured data.
- **Never pin an exact warning or error count from a module that itself trips
  the lint being counted.** The module raises the count by one the moment it is
  committed — a measurement that includes the measurer. Assert on the warning
  you mean by matching it, not on how many there are.
- **A scope claim about a diff belongs on the branch, not in the suite.** "This
  item did not touch X" is decided by `aide scope` against the item's declared
  paths (§1 → authorised paths); written as a test it asserts something that
  stops being true the moment the item merges — and on a stacked queue, where
  the item's base is the queue branch and not `main`, it reports every sibling
  item's legitimate change as this item's violation. **Deriving the base from
  `aide scope` is not the repair**: the verb reads the *current* branch's
  recorded base, and `aide merge` re-runs the suite from the merge target. Nor
  is a skip guard, which leaves the test permanently skipped once the claim
  branch is deleted. `aide check` warns on both literal shapes.
- **Assert a derived value is recognisable *before* asserting anything about
  it.** A glob that matched nothing, a capture that came back empty, a slice
  taken from a failed `find()` — each yields a value that flows into the
  assertion and passes while checking nothing at all. A test that cannot fail is
  worse than no test.
