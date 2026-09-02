"""Tests for the scope-claim lint — conventions.md §6 and §1 → authorised paths.

The recorded defect (issue #132): an acceptance criterion asked for a scope
guard, and it was written as a suite assertion shelling out to
``git diff --name-only main...HEAD``. Under a stacked queue the item's base is
the *queue branch*, so `main` is stale by the whole queue and every sibling
item's already-merged, entirely legitimate change was reported as a violation by
the current item. The obvious repair — deriving the base from `aide scope` —
fails in the same direction for a different reason, and a skip guard leaves the
test permanently skipped once the claim branch is gone.

Two independent items in one consumer wrote the same wrong shape. That is the
signature of a missing check: the rule was already written down twice, in §1 →
authorised paths and in `cmd_scope`'s own docstring, and reached neither the
spec-author writing the criterion nor the test-writer implementing it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_scope_claims", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _repo(tmp_path: Path, main_branch: str = "main") -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        f'[project]\nname = "Demo"\ntests_dir = "tests"\n\n'
        f'[git]\nmain_branch = "{main_branch}"\n', encoding="utf-8")
    return repo


def _warn(repo: Path):
    return aide.scope_claim_test_warnings(repo, aide.load_config(repo))


def _write(repo: Path, name: str, body: str) -> None:
    (repo / "tests" / name).write_text(body, encoding="utf-8")


def test_flags_a_hardcoded_diff_range(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo, "test_data_layout.py",
           "import subprocess\n"
           "def test_scope():\n"
           "    out = subprocess.run(['git', 'diff', '--name-only',\n"
           "                          'main...HEAD', '--', 'src/pkg/thing.py'],\n"
           "                         capture_output=True, encoding='utf-8')\n"
           "    assert not out.stdout\n")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/test_data_layout.py:4" in warnings[0]
    assert "Asserts against" in warnings[0]


def test_flags_the_two_dot_and_reversed_spellings(tmp_path: Path):
    """A range is a range. `main..HEAD` and `HEAD...main` make the same claim,
    and a lint that knew one spelling would send the author to the others."""
    for i, rng in enumerate(("main..HEAD", "HEAD...main", "origin/main...HEAD")):
        repo = _repo(tmp_path / str(i))
        _write(repo, "test_thing.py", f'RANGE = "{rng}"\n')
        assert len(_warn(repo)) == 1, rng


def test_flags_the_conventional_names_whatever_the_config_says(tmp_path: Path):
    """`main` and `master` are flagged even when neither is this project's base.

    The shape is copied between projects, so a consumer whose `main_branch` is
    `develop` and whose test says `main...HEAD` has written the same wrong
    assertion — and the lint that only knew its own config would be silent on
    exactly the case where the author was working from someone else's example.
    """
    repo = _repo(tmp_path, main_branch="develop")
    _write(repo, "test_a.py", 'R = "main...HEAD"\n')
    assert len(_warn(repo)) == 1
    repo_b = _repo(tmp_path / "b", main_branch="develop")
    _write(repo_b, "test_b.py", 'R = "develop...HEAD"\n')
    assert len(_warn(repo_b)) == 1


def test_flags_a_shell_out_to_aide_scope(tmp_path: Path):
    """The repair the consumer tried second, and it is wrong too: the verb
    resolves its base from the current branch, and `aide merge` re-runs the
    suite from the merge target."""
    repo = _repo(tmp_path)
    _write(repo, "test_scope_guard.py",
           "import subprocess\n"
           "def test_scope():\n"
           "    r = subprocess.run(['python', '.aide/scripts/aide.py', 'scope', '18'],\n"
           "                       capture_output=True, encoding='utf-8')\n"
           "    assert r.returncode == 0\n")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/test_scope_guard.py:3" in warnings[0]
    assert "aide scope" in warnings[0]


def test_a_computed_base_is_deliberately_not_reported(tmp_path: Path):
    """The false positive this lint refuses to have.

    A test that computes its base — `git merge-base HEAD origin/main`, then a
    diff — is a claim about the *branch*, not about an item's scope, and it is
    legitimate: this framework's own `tests/test_repo_versioning.py` is exactly
    that shape and enforces the version gate with it. Nothing in the source
    tells the two apart, so the lint decides only what is literal and §6's rule
    binds where it cannot look.
    """
    repo = _repo(tmp_path)
    _write(repo, "test_version_gate.py",
           "import subprocess\n"
           "def test_gate():\n"
           "    base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/main'],\n"
           "                          capture_output=True, encoding='utf-8').stdout.strip()\n"
           "    changed = subprocess.run(['git', 'diff', '--name-only', base, 'HEAD'],\n"
           "                             capture_output=True, encoding='utf-8').stdout\n"
           "    assert changed is not None\n")
    assert _warn(repo) == []


def test_an_ordinary_git_call_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo, "test_branch.py",
           "import subprocess\n"
           "def test_branch():\n"
           "    b = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],\n"
           "                       capture_output=True, encoding='utf-8')\n"
           "    assert b.stdout.strip()\n")
    assert _warn(repo) == []


def test_a_shell_out_to_another_verb_is_not_a_scope_claim(tmp_path: Path):
    """`cli_subprocess_test_warnings` owns the boundary; this lint owns the
    claim. A test driving `aide check` is the other lint's business, and
    reporting it here would say something untrue about it."""
    repo = _repo(tmp_path)
    _write(repo, "test_check.py",
           "import subprocess\n"
           "def test_check():\n"
           "    subprocess.run(['python', '.aide/scripts/aide.py', 'check'])\n")
    assert _warn(repo) == []


def test_one_warning_per_file(tmp_path: Path):
    repo = _repo(tmp_path)
    _write(repo, "test_thing.py",
           'A = "main...HEAD"\nB = "main...HEAD"\nC = "main...HEAD"\n')
    assert len(_warn(repo)) == 1


def test_undecodable_file_does_not_crash_the_check(tmp_path: Path):
    """A lint that raises on one odd file takes the whole `aide check` with it."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_binary.py").write_bytes(b"\xff\xfe\x00\x01 not utf-8")
    assert _warn(repo) == []


def test_missing_tests_dir_is_silent(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\n', encoding="utf-8")
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
    _write(repo, "test_thing.py", 'R = "main...HEAD"\n')

    _, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert any("diff-time scope claim" in w for w in warnings)
