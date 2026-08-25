"""Tests for `aide check` in a repo that adopted part of the framework.

The recorded defect (issue #57): `run_checks` early-returned a hard error the
moment `progress.md` was absent, which conflated two unrelated situations — a
loop repo that lost its central document, and a repo that never had a document
set because it adopted only the conventions and the CLI. The second case is not
an error, and treating it as one made the three *test-hygiene* lints
unreachable for exactly the repos most exposed to what they catch. This
framework's own repository was one of them: it has no `docs/aide/`, its tests do
installer and CLI path work, and it runs on an ubuntu + windows matrix.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_partial", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _repo(tmp_path: Path, *, docs: bool = False, progress: bool = False) -> Path:
    """A repo with a `tests_dir` and, optionally, a document set."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\ndocs_dir = "docs/aide"\n',
        encoding="utf-8")
    if docs:
        (repo / "docs" / "aide").mkdir(parents=True)
    if progress:
        (repo / "docs" / "aide" / "progress.md").write_text(
            "# P\n\n| 1 | S | G | 📋 |\n\n| G1 | O | 📋 |\n\n## Stage 1 — S — 📋\n",
            encoding="utf-8")
    return repo


def _offending_test(repo: Path) -> None:
    """A test file carrying the one defect `separator_dependent_test_warnings`
    decides — the lint stands in for all three here."""
    (repo / "tests" / "test_thing.py").write_text(
        "from pathlib import Path\n"
        "def test_x(root, p):\n"
        "    assert True, f\"{p.relative_to(root)} is wrong\"\n",
        encoding="utf-8")


# --------------------------------------------------------------------------- #
# No document set: not an error, and the repo-agnostic lints still run
# --------------------------------------------------------------------------- #
def test_absent_docs_dir_is_not_an_error(tmp_path: Path):
    repo = _repo(tmp_path)
    errors, _ = aide.run_checks(repo, aide.load_config(repo))
    assert errors == []


def test_test_hygiene_lints_reach_a_repo_with_no_document_set(tmp_path: Path):
    """The whole point of the change: these lints read `tests_dir`, never
    `docs_dir`, so a missing `docs_dir` must not discard their findings."""
    repo = _repo(tmp_path)
    _offending_test(repo)
    errors, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert errors == []
    assert any("differs on Windows" in w for w in warnings)


def test_check_exits_zero_and_says_why_when_there_is_no_document_set(
        tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    assert "notice:" in out and "docs/aide" in out
    # "OK" must not be readable as "the documents were checked and are fine".
    assert "only the repo-agnostic checks ran" in out


def test_notice_names_the_configured_docs_dir_not_the_default(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\ndocs_dir = "planning"\n',
        encoding="utf-8")
    assert aide.main(["--repo", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    assert "planning" in out


def test_notice_carries_no_native_separator(tmp_path: Path, capsys):
    """The same rule the lints enforce, applied to the message they made
    reachable: a nested `docs_dir` must render POSIX on every platform."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ndocs_dir = "docs/planning/aide"\n', encoding="utf-8")
    assert aide.main(["--repo", str(repo), "check"]) == 0
    notice = [l for l in capsys.readouterr().out.splitlines() if l.startswith("notice:")]
    assert notice and "\\" not in notice[0]


# --------------------------------------------------------------------------- #
# A document set that lost its progress.md: still the error it always was
# --------------------------------------------------------------------------- #
def test_docs_dir_without_progress_is_still_an_error(tmp_path: Path):
    repo = _repo(tmp_path, docs=True)
    errors, _ = aide.run_checks(repo, aide.load_config(repo))
    assert len(errors) == 1
    assert errors[0].startswith("missing ")
    assert errors[0].endswith("progress.md")


def test_check_fails_when_a_loop_repo_lost_its_progress(tmp_path: Path, capsys):
    repo = _repo(tmp_path, docs=True)
    assert aide.main(["--repo", str(repo), "check"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "notice:" not in out  # the document set exists; nothing was skipped


def test_a_present_document_set_still_gets_its_document_checks(tmp_path: Path, capsys):
    """Guard against the fix over-reaching: a real loop repo must be unaffected."""
    repo = _repo(tmp_path, docs=True, progress=True)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert "notice:" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# A docs_dir that is not a directory: a third case, and a real error
# --------------------------------------------------------------------------- #
def _misconfigured(tmp_path: Path) -> Path:
    """A repo whose `docs_dir` names a file."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ndocs_dir = "NOTES.md"\n', encoding="utf-8")
    (repo / "NOTES.md").write_text("# notes\n", encoding="utf-8")
    return repo


def test_a_docs_dir_that_is_not_a_directory_is_an_error(tmp_path: Path):
    """Folded into the partial-adoption branch this would report "this repo has
    no AIDE document set" and exit 0 — a typo in aide.toml passing as a
    deliberate choice not to adopt the loop."""
    repo = _misconfigured(tmp_path)
    errors, _ = aide.run_checks(repo, aide.load_config(repo))
    assert len(errors) == 1
    assert "not a directory" in errors[0] and "NOTES.md" in errors[0]


def test_a_misconfigured_docs_dir_gets_no_partial_adoption_notice(
        tmp_path: Path, capsys):
    repo = _misconfigured(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 1
    out = capsys.readouterr().out
    assert "notice:" not in out
    assert "no AIDE document set" not in out


def test_the_misconfiguration_error_names_the_key_to_fix(tmp_path: Path, capsys):
    repo = _misconfigured(tmp_path)
    aide.main(["--repo", str(repo), "check"])
    assert "docs_dir" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# --queue must not silently pass just because there is nowhere to look
# --------------------------------------------------------------------------- #
def test_queue_check_still_fails_with_no_document_set(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "check", "--queue", "3"]) == 1


def test_the_notice_is_withheld_on_a_queue_run(tmp_path: Path, capsys):
    """`--queue` sends the cross-spec check looking for a queue under the same
    absent directory, so it runs and errors. Printing "only the repo-agnostic
    checks ran" next to that error would be false — and the notice only ever
    existed to stop a *pass* being over-read."""
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "check", "--queue", "3"]) == 1
    out = capsys.readouterr().out
    assert "notice:" not in out
    assert "FAIL" in out


def test_the_notice_still_appears_on_a_queue_run_that_has_a_document_set(
        tmp_path: Path, capsys):
    """Guard against the gate over-reaching in the other direction: a repo WITH
    a document set never got the notice, and still must not."""
    repo = _repo(tmp_path, docs=True, progress=True)
    assert aide.main(["--repo", str(repo), "check", "--queue", "3"]) == 1
    assert "notice:" not in capsys.readouterr().out
