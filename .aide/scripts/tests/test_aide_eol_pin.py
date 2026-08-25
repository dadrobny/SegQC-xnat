"""Tests for the `.gitattributes` `eol=lf` lint — conventions.md §6.

The rule was stated in §6 and §1 and enforced by nothing. Without the pin,
`core.autocrlf` rewrites a committed fixture on a Windows checkout and every
byte comparison against it fails **on Windows only** — the platform §7 says no
gate in this loop ever sees. The recorded instance cost 13 red tests across
three modules, invisible to every local run.

Its sibling rule got a lint in 1.11.0 because a repo-root string match could
decide it. This one is fuzzier, so the tests below are weighted towards the
false positives that would make it noise: a plain read, a substring assertion, a
determinism check between two generated files. A lint that cries wolf stops
being read, and silence on those cases is the feature.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_eol", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _repo(tmp_path: Path, gitattributes: str = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\n', encoding="utf-8")
    if gitattributes is not None:
        (repo / ".gitattributes").write_text(gitattributes, encoding="utf-8")
    return repo


def _fixture(repo: Path, rel: str, body: str = "{}\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _warn(repo: Path):
    return aide.gitattributes_eol_pin_warnings(repo, aide.load_config(repo))


_COMPARE = '''\
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = REPO_ROOT / "tests" / "golden" / "report.json"


def test_it(tmp_path):
    written = tmp_path / "report.json"
    assert written.read_bytes() == GOLDEN.read_bytes()
'''


# --------------------------------------------------------------------------- #
# it fires on the recorded defect
# --------------------------------------------------------------------------- #
def test_unpinned_committed_fixture_is_flagged(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="*.nii.gz binary\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "tests/golden/report.json" in warnings[0]
    assert "conventions.md §6" in warnings[0]
    assert "text eol=lf" in warnings[0]


def test_a_pin_silences_it(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="tests/golden/*.json text eol=lf\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert _warn(repo) == []


def test_no_gitattributes_at_all_says_so(tmp_path: Path):
    repo = _repo(tmp_path)
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "no .gitattributes" in warnings[0]


def test_a_hashed_fixture_counts_as_byte_exact(tmp_path: Path):
    """A digest is a byte-exactness claim by another name — the shape the
    recorded whole-tree-hash failures took."""
    repo = _repo(tmp_path, gitattributes="")
    _fixture(repo, "src/thing.py", "x = 1\n")
    (repo / "tests" / "test_h.py").write_text(
        'import hashlib\n'
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'PINNED = ROOT / "src" / "thing.py"\n'
        'def test_it():\n'
        '    h = hashlib.sha256()\n'
        '    h.update(PINNED.read_bytes())\n',
        encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1
    assert "src/thing.py" in warnings[0]


# --------------------------------------------------------------------------- #
# precision: the cases that must stay silent
# --------------------------------------------------------------------------- #
def test_a_plain_read_is_not_a_byte_comparison(tmp_path: Path):
    """The false positive that made the first draft unusable: a helper that
    reads a committed file so a caller can assert a *substring*. Universal
    newlines make it immune to the CRLF rewrite, so a pin buys it nothing."""
    repo = _repo(tmp_path, gitattributes="")
    _fixture(repo, "docs/progress.md", "# Progress\n")
    (repo / "tests" / "test_p.py").write_text(
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'PROGRESS = ROOT / "docs" / "progress.md"\n'
        'def _read():\n'
        '    return PROGRESS.read_text(encoding="utf-8")\n'
        'def test_it():\n'
        '    assert "Progress" in _read()\n',
        encoding="utf-8")
    assert _warn(repo) == []


def test_two_generated_files_compared_to_each_other_are_silent(tmp_path: Path):
    """A determinism check. Neither side is committed, so neither needs a pin —
    and these are the majority of `read_bytes()` calls in a real suite."""
    repo = _repo(tmp_path, gitattributes="")
    (repo / "tests" / "test_d.py").write_text(
        'def test_it(tmp_path):\n'
        '    a = tmp_path / "one.json"\n'
        '    b = tmp_path / "two.json"\n'
        '    assert a.read_bytes() == b.read_bytes()\n',
        encoding="utf-8")
    assert _warn(repo) == []


def test_a_path_that_does_not_exist_is_not_reported(tmp_path: Path):
    """Resolves but is absent: a generated artifact, not a committed fixture."""
    repo = _repo(tmp_path, gitattributes="")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert _warn(repo) == []


def test_a_substring_or_ordering_test_is_not_flagged(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'GOLDEN = ROOT / "tests" / "golden" / "report.json"\n'
        'def test_it():\n'
        '    assert b"{" in GOLDEN.read_bytes()\n',
        encoding="utf-8")
    assert _warn(repo) == []


def test_a_path_outside_the_repo_is_not_ours_to_pin(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="")
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}\n", encoding="utf-8")
    (repo / "tests" / "test_o.py").write_text(
        'from pathlib import Path\n'
        f'OUT = Path({str(outside.resolve().as_posix())!r})\n'
        'def test_it(tmp_path):\n'
        '    assert (tmp_path / "x").read_bytes() == OUT.read_bytes()\n',
        encoding="utf-8")
    assert _warn(repo) == []


# --------------------------------------------------------------------------- #
# the pattern matcher follows git's rules, not fnmatch's
# --------------------------------------------------------------------------- #
def test_a_single_star_does_not_cross_a_directory_separator(tmp_path: Path):
    """`fnmatch` would call this pinned; git does not, and a false *silence*
    here is the failure the lint exists to prevent."""
    repo = _repo(tmp_path, gitattributes="tests/*.json text eol=lf\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    warnings = _warn(repo)
    assert len(warnings) == 1


def test_a_pattern_with_no_slash_matches_at_any_depth(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="*.json text eol=lf\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert _warn(repo) == []


def test_double_star_crosses_separators(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="tests/**/*.json text eol=lf\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert _warn(repo) == []


def test_a_pin_without_eol_lf_does_not_count(tmp_path: Path):
    """`binary` and a bare `text` are not the pin: only `eol=lf` stops the
    rewrite."""
    repo = _repo(tmp_path, gitattributes="tests/golden/*.json text\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert len(_warn(repo)) == 1


def test_comments_and_blank_lines_are_ignored(tmp_path: Path):
    repo = _repo(
        tmp_path,
        gitattributes="# tests/golden/*.json text eol=lf\n\n*.nii.gz binary\n")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(_COMPARE, encoding="utf-8")
    assert len(_warn(repo)) == 1


# --------------------------------------------------------------------------- #
# robustness
# --------------------------------------------------------------------------- #
def test_missing_tests_dir_is_silent(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ntests_dir = "tests"\n', encoding="utf-8")
    assert _warn(repo) == []


def test_an_unparseable_test_file_does_not_crash(tmp_path: Path):
    repo = _repo(tmp_path, gitattributes="")
    (repo / "tests" / "test_broken.py").write_text("def (:\n", encoding="utf-8")
    assert _warn(repo) == []


def test_one_warning_per_file_and_fixture_pair(tmp_path: Path):
    """The same golden compared twice in one file is one thing to fix."""
    repo = _repo(tmp_path, gitattributes="")
    _fixture(repo, "tests/golden/report.json")
    (repo / "tests" / "test_g.py").write_text(
        'from pathlib import Path\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'GOLDEN = ROOT / "tests" / "golden" / "report.json"\n'
        'def test_a(tmp_path):\n'
        '    assert (tmp_path / "x").read_bytes() == GOLDEN.read_bytes()\n'
        'def test_b(tmp_path):\n'
        '    assert (tmp_path / "y").read_bytes() == GOLDEN.read_bytes()\n',
        encoding="utf-8")
    assert len(_warn(repo)) == 1
