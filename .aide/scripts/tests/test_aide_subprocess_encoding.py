"""Tests for the subprocess `encoding=` lint — conventions.md §6.

The recorded defect (issue #126). Six items in one consumer queue each
independently wrote `subprocess.run(..., capture_output=True, text=True)` with
no `encoding=`. Every one passed the Linux-only validator, because
`locale.getpreferredencoding()` is UTF-8 there. On `windows-latest` the same
bytes came back cp1252-decoded: one test raised a `KeyError` on a mangled
em-dash heading, and — the reason this is a lint rather than advice — an
emoji-diff guard in another **matched nothing and reported PASS**. A false
negative is the worst outcome this loop has available, and §7 says no gate
inside the loop ever sees the platform that produces it.

Weighted like its eol-pin neighbour: the firing cases first, then the silences
that keep it worth reading. `check_call` decodes nothing, `text=False` asks for
bytes, and an explicit `encoding=` is the fix — flagging any of those would
teach a reader to skip the lint's output, which costs more than the class does.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_subproc_enc", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\n', encoding="utf-8")
    return repo


def _write(repo: Path, body: str, name: str = "test_thing.py") -> None:
    (repo / "tests" / name).write_text(body, encoding="utf-8")


def _warn(repo: Path):
    return aide.subprocess_encoding_test_warnings(repo, aide.load_config(repo))


# --------------------------------------------------------------------------- #
# it fires on the recorded defect
# --------------------------------------------------------------------------- #
def test_flags_the_recorded_shape(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "def test_it():\n"
           "    r = subprocess.run(['git', 'log'], capture_output=True, text=True)\n"
           "    assert r.stdout\n")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/test_thing.py:3" in warnings[0]
    assert "conventions.md §6" in warnings[0]
    assert 'encoding="utf-8"' in warnings[0]


def test_flags_the_universal_newlines_spelling(tmp_path: Path):
    """The pre-3.7 name is still accepted, and is the one an author copies from
    an old answer — which is where this class comes from."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "out = subprocess.check_output(['git', 'log'], universal_newlines=True)\n")
    assert len(_warn(repo)) == 1


def test_flags_popen(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "p = subprocess.Popen(['x'], stdout=subprocess.PIPE, text=True)\n")
    assert len(_warn(repo)) == 1


def test_flags_a_bare_imported_run(tmp_path: Path):
    """`from subprocess import run` reaches the same decoder by another name."""
    repo = _repo(tmp_path)
    _write(repo,
           "from subprocess import run\n"
           "r = run(['x'], capture_output=True, text=True)\n")
    assert len(_warn(repo)) == 1


def test_flags_a_non_literal_text_argument(tmp_path: Path):
    """A call that *may* decode and names no codec is wrong in the same way as
    one that certainly does; the source cannot say which this is."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "def go(as_text):\n"
           "    return subprocess.run(['x'], capture_output=True, text=as_text)\n")
    assert len(_warn(repo)) == 1


# --------------------------------------------------------------------------- #
# precision: the cases that must stay silent
# --------------------------------------------------------------------------- #
def test_an_explicit_encoding_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "r = subprocess.run(['x'], capture_output=True, text=True, "
           "encoding='utf-8')\n")
    assert _warn(repo) == []


def test_bytes_are_silent(tmp_path: Path):
    """No `text=` at all: the caller decodes deliberately, or does not decode."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "out = subprocess.run(['x'], capture_output=True).stdout.decode('utf-8')\n")
    assert _warn(repo) == []


def test_text_false_is_silent(tmp_path: Path):
    """`text=False` asks for bytes. Flagging it would be a warning with no fix."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "r = subprocess.run(['x'], capture_output=True, text=False)\n")
    assert _warn(repo) == []


def test_check_call_is_silent(tmp_path: Path):
    """`call` and `check_call` return an exit status and never a capture, so a
    `text=` on one of them decodes nothing. This is the narrowing that keeps
    every warning the lint emits a call that really would decode."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "subprocess.check_call(['x'], text=True)\n"
           "subprocess.call(['x'], text=True)\n")
    assert _warn(repo) == []


def test_an_unrelated_run_carrying_text_is_silent(tmp_path: Path):
    """A `run(...)` that is not subprocess's, **with the keyword present**.

    The version of this test written first passed `check=True` and so proved
    nothing: it would have stayed silent under a lint matching on method name
    alone, which is what the lint then did. Review caught that. A `Runner` with
    its own `text=` parameter is the shape that separates matching a name from
    resolving an import, so that is what this asserts on.
    """
    repo = _repo(tmp_path)
    _write(repo,
           "class Runner:\n"
           "    def run(self, args, text=True):\n"
           "        return args\n"
           "def test_it():\n"
           "    assert Runner().run(['x'], text=True) == ['x']\n")
    assert _warn(repo) == []


def test_a_module_that_never_imports_subprocess_is_silent(tmp_path: Path):
    """The cheap half of the same guard, and the common one: no import, no
    subprocess, whatever the call is spelled like."""
    repo = _repo(tmp_path)
    _write(repo,
           "import shutil\n"
           "def test_it(proc):\n"
           "    proc.check_output(['x'], universal_newlines=True)\n")
    assert _warn(repo) == []


def test_an_aliased_import_is_still_reported(tmp_path: Path):
    """Resolving the import must not become a way to hide from the lint —
    `import subprocess as sp` is the same call by another name."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess as sp\n"
           "r = sp.run(['x'], capture_output=True, text=True)\n")
    assert len(_warn(repo)) == 1


def test_a_star_import_is_still_reported(tmp_path: Path):
    """The false negative resolving imports introduced, caught in round two.

    `from subprocess import *` binds `run` without naming it, so a resolver
    keyed on the names in the statement saw nothing and went quiet on a call
    the name-only matching it replaced had reported. Trading a false positive
    for a false negative is the wrong direction — this section's whole argument
    for the lint is that a false negative is the worst outcome available.
    """
    repo = _repo(tmp_path)
    _write(repo,
           "from subprocess import *\n"
           "r = run(['x'], capture_output=True, text=True)\n")
    assert len(_warn(repo)) == 1


def test_an_aliased_from_import_is_still_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo,
           "from subprocess import check_output as co\n"
           "out = co(['x'], text=True)\n")
    assert len(_warn(repo)) == 1


# --------------------------------------------------------------------------- #
# reporting and robustness
# --------------------------------------------------------------------------- #
def test_one_warning_per_file(tmp_path: Path):
    """Three calls in one module are one file to open and one habit to fix."""
    repo = _repo(tmp_path)
    _write(repo,
           "import subprocess\n"
           "a = subprocess.run(['x'], capture_output=True, text=True)\n"
           "b = subprocess.run(['y'], capture_output=True, text=True)\n"
           "c = subprocess.check_output(['z'], text=True)\n")
    assert len(_warn(repo)) == 1


def test_each_offending_file_is_named(tmp_path: Path):
    repo = _repo(tmp_path)
    body = ("import subprocess\n"
            "r = subprocess.run(['x'], capture_output=True, text=True)\n")
    _write(repo, body, "test_one.py")
    _write(repo, body, "test_two.py")
    warnings = _warn(repo)
    assert len(warnings) == 2
    assert {"tests/test_one.py", "tests/test_two.py"} == {
        w.split(":")[0] for w in warnings}


def test_missing_tests_dir_is_silent(tmp_path: Path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "aide.toml").write_text('[project]\nname = "D"\n', encoding="utf-8")
    assert _warn(repo) == []


def test_an_unparseable_test_file_does_not_crash(tmp_path: Path):
    """A lint that raises on one odd file takes the whole `aide check` with it."""
    repo = _repo(tmp_path)
    _write(repo, "def (:\n", "test_broken.py")
    assert _warn(repo) == []


def test_reaches_run_checks(tmp_path: Path):
    """The lint is only useful if `aide check` actually runs it."""
    repo = _repo(tmp_path)
    ddir = repo / "docs" / "aide"
    ddir.mkdir(parents=True)
    (ddir / "progress.md").write_text("# P\n\n## Stage 1 — S — 📋\n", encoding="utf-8")
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\ndocs_dir = "docs/aide"\n',
        encoding="utf-8")
    _write(repo,
           "import subprocess\n"
           "r = subprocess.run(['x'], capture_output=True, text=True)\n")

    _, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert any("no encoding=" in w for w in warnings)
