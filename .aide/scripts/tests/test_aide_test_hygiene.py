"""Tests for the absolute-path lint — conventions.md §6's one decidable rule.

The recorded defect: a test pinned the authoring sandbox's own filesystem path
instead of resolving relative to the test file. Because that path *is* where the
project sits on that machine, it passed the builder's run, both validator
rounds, and a fresh clone into a different directory — an absolute path ignores
where the process runs from. On CI the glob matched nothing and all four legs
failed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_hygiene", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\n', encoding="utf-8")
    return repo


def _warn(repo: Path):
    return aide.absolute_path_test_warnings(repo, aide.load_config(repo))


def test_flags_the_repos_own_absolute_path(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_thing.py").write_text(
        f'GOLDEN = Path("{repo.resolve().as_posix()}/tests/corpus/golden")\n',
        encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/test_thing.py:1" in warnings[0]
    assert "conventions.md §6" in warnings[0]


def test_clean_test_file_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_thing.py").write_text(
        "GOLDEN = Path(__file__).resolve().parents[1] / 'corpus'\n", encoding="utf-8")
    assert _warn(repo) == []


def test_an_unrelated_absolute_path_is_not_flagged(tmp_path: Path):
    """Only this repository's own root matches — that is what makes the rule
    exact, with no judgement call and no false positive to argue about."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_thing.py").write_text(
        'DATA = Path("/usr/share/dict/words")\n', encoding="utf-8")
    assert _warn(repo) == []


def test_one_warning_per_file(tmp_path: Path):
    repo = _repo(tmp_path)
    root = repo.resolve().as_posix()
    (repo / "tests" / "test_thing.py").write_text(
        f'A = "{root}/a"\nB = "{root}/b"\nC = "{root}/c"\n', encoding="utf-8")
    assert len(_warn(repo)) == 1


def test_pycache_is_skipped(tmp_path: Path):
    repo = _repo(tmp_path)
    cache = repo / "tests" / "__pycache__"
    cache.mkdir()
    (cache / "test_stale.py").write_text(
        f'X = "{repo.resolve().as_posix()}"\n', encoding="utf-8")
    assert _warn(repo) == []


def test_missing_tests_dir_is_silent(tmp_path: Path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "aide.toml").write_text('[project]\nname = "D"\n', encoding="utf-8")
    assert _warn(repo) == []


def test_nested_test_files_are_scanned(tmp_path: Path):
    repo = _repo(tmp_path)
    nested = repo / "tests" / "unit" / "deep"
    nested.mkdir(parents=True)
    (nested / "test_deep.py").write_text(
        f'X = "{repo.resolve().as_posix()}/x"\n', encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/unit/deep/test_deep.py" in warnings[0]


def test_flags_the_escaped_backslash_spelling(tmp_path: Path):
    """The common Windows literal is `"C:\\\\path\\\\to\\\\repo"` — escaped, so
    the source text holds doubled backslashes while `str(root)` holds single
    ones. Missing it would leave this portability lint unable to catch the most
    likely Windows spelling of the defect it exists for.

    Honest limit, per conventions.md §6: on POSIX the three needle spellings
    collapse to one string, so here this asserts the same thing as the plain
    case. It is a real test only on the Windows CI leg — which is exactly why
    that leg exists, and why this is not evidence the branch works until CI
    says so.
    """
    repo = _repo(tmp_path)
    escaped = str(repo.resolve()).replace("\\", "\\\\")
    (repo / "tests" / "test_thing.py").write_text(
        f'GOLDEN = Path("{escaped}/tests/corpus")\n', encoding="utf-8")
    assert len(_warn(repo)) == 1


def test_flags_the_native_separator_spelling(tmp_path: Path):
    """A raw string keeps the OS-native separators verbatim."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_thing.py").write_text(
        f'GOLDEN = Path(r"{repo.resolve()}")\n', encoding="utf-8")
    assert len(_warn(repo)) == 1


def test_tests_dir_outside_the_repo_does_not_crash(tmp_path: Path):
    """`tests_dir` may be configured absolute, so `relative_to` can raise. A
    lint that raises takes the whole `aide check` down instead of reporting."""
    repo = _repo(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "test_thing.py").write_text(
        f'X = "{repo.resolve().as_posix()}/x"\n', encoding="utf-8")
    (repo / "aide.toml").write_text(
        f'[project]\nname = "Demo"\ntests_dir = "{outside.as_posix()}"\n',
        encoding="utf-8")

    warnings = _warn(repo)          # must not raise
    assert len(warnings) == 1
    assert "elsewhere/test_thing.py" in warnings[0]


def test_undecodable_file_does_not_crash_the_check(tmp_path: Path):
    """A lint that raises on one odd file takes the whole `aide check` with it."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_binary.py").write_bytes(b"\xff\xfe\x00\x01 not utf-8")
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
    (repo / "tests" / "test_thing.py").write_text(
        f'X = "{repo.resolve().as_posix()}/x"\n', encoding="utf-8")

    _, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert any("absolute path" in w for w in warnings)
