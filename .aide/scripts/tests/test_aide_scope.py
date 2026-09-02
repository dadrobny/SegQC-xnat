"""Tests for ``aide scope`` — a branch's diff vs the item's authorised paths.

The parsing and matching helpers are pure, so most of this file needs no git at
all. The end-to-end tests build a throwaway repository under ``tmp_path``, the
same way ``test_aide_git.py`` does, so nothing touches the real project.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_scope", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"

[git]
mode = "local"
main_branch = "main"
branch_prefix = "aide/"
"""

SPEC = """\
# Item 042 — Demo item

> **Stage:** 1 — Rules

## Description

Something.

## Authorised paths

**May change:**

- `src/demo/rules.py` — the new rule
- `tests/golden/*.json` — regenerated here

**Asserts against:**

- `docs/aide/catalogue.json` — AC7 recomputes its counts live

## Testing Strategy

One test per AC.
"""


def _run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding="utf-8")


# --------------------------------------------------------------------------- #
# parse_authorised_paths
# --------------------------------------------------------------------------- #
def test_parse_splits_the_two_sub_lists():
    got = aide.parse_authorised_paths(SPEC)
    assert got.may_change == ["src/demo/rules.py", "tests/golden/*.json"]
    assert got.asserts_against == ["docs/aide/catalogue.json"]


def test_parse_takes_the_path_not_the_reason():
    """The reason after the path is prose — stripping outer backticks off the
    whole bullet would swallow it into the pattern and match nothing."""
    got = aide.parse_authorised_paths(
        "## Authorised paths\n\n- `src/a.py` — because `b.py` moved\n")
    assert got.may_change == ["src/a.py"]


def test_parse_missing_section_is_none_not_empty():
    """None (absent) and [] (present, empty) need different remedies, so the
    parser must not collapse them — neither may be read as 'unconstrained'."""
    assert aide.parse_authorised_paths("# Item 042\n\n## Description\n\nx\n") is None
    empty = aide.parse_authorised_paths("## Authorised paths\n\n## Next\n")
    assert empty == aide.AuthorisedPaths([], [])


def test_parse_flat_legacy_list_reads_as_may_change():
    """Specs written before the sub-list labels existed put bullets straight
    under the heading; those must not parse as an empty May-change list."""
    got = aide.parse_authorised_paths(
        "## Authorised paths\n\n- `src/a.py`\n- `src/b.py`\n")
    assert got.may_change == ["src/a.py", "src/b.py"]
    assert got.asserts_against == []


def test_parse_stops_at_the_next_heading():
    got = aide.parse_authorised_paths(SPEC)
    assert "One test per AC." not in got.may_change


def test_parse_skips_unfilled_slots_and_none():
    """An unfilled `{{slot}}` is already an `aide check` error; reporting it
    here too would bill one authoring slip twice."""
    got = aide.parse_authorised_paths(
        "## Authorised paths\n\n**May change:**\n\n- `{{path or glob}}` — {{why}}\n"
        "\n**Asserts against:**\n\n- None.\n")
    assert got == aide.AuthorisedPaths([], [])


def test_parse_keeps_a_leading_dot_on_a_dotfile():
    """`lstrip("./")` strips leading *characters* from that set, silently
    renaming the dotfiles specs routinely authorise into paths that match
    nothing git reports. Both forms below are real, from merged consumer specs."""
    got = aide.parse_authorised_paths(
        "## Authorised paths\n\n- `.gitattributes` — pin the fixtures\n"
        "- `.github/workflows/ci.yml` — the matrix job\n")
    assert got.may_change == [".gitattributes", ".github/workflows/ci.yml"]


def test_match_dotfile_round_trips():
    assert aide.path_matches(".gitattributes", ".gitattributes")
    assert aide.path_matches(".github/workflows/ci.yml", ".github/workflows/*.yml")


def test_parse_accepts_label_punctuation_variants():
    got = aide.parse_authorised_paths(
        "## Authorised paths\n\nMay change\n\n- `a.py`\n\n**Asserts against**\n\n- `b.json`\n")
    assert got.may_change == ["a.py"]
    assert got.asserts_against == ["b.json"]


# --------------------------------------------------------------------------- #
# path_matches
# --------------------------------------------------------------------------- #
def test_match_exact_path():
    assert aide.path_matches("src/a.py", "src/a.py")
    assert not aide.path_matches("src/ab.py", "src/a.py")


def test_match_subtree_wildcard():
    assert aide.path_matches("src/deep/down/a.py", "src/**")
    assert aide.path_matches("src", "src/**")
    assert not aide.path_matches("srcfoo/a.py", "src/**")


def test_match_single_star_glob_does_not_cross_a_slash():
    """The defect this verb exists to fix: `dir/*.ext` is what specs actually
    write, and fnmatch's `*` crossing `/` would widen it to a whole subtree."""
    assert aide.path_matches("tests/golden/a.json", "tests/golden/*.json")
    assert not aide.path_matches("tests/golden/nested/a.json", "tests/golden/*.json")
    assert not aide.path_matches("tests/golden/a.txt", "tests/golden/*.json")


def test_match_is_case_sensitive():
    assert not aide.path_matches("SRC/A.PY", "src/*.py")


def test_match_normalises_a_leading_dot_slash():
    assert aide.path_matches("src/a.py", "./src/a.py")


# --------------------------------------------------------------------------- #
# scope_findings
# --------------------------------------------------------------------------- #
def test_findings_separate_unauthorised_from_contradiction():
    authorised = aide.AuthorisedPaths(["src/a.py"], ["docs/pinned.json"])
    unauthorised, contradictions = aide.scope_findings(
        ["src/a.py", "src/b.py", "docs/pinned.json"], authorised)
    assert unauthorised == ["src/b.py", "docs/pinned.json"]
    assert contradictions == ["docs/pinned.json"]


def test_findings_honour_the_always_authorised_set():
    authorised = aide.AuthorisedPaths(["src/a.py"], [])
    unauthorised, _ = aide.scope_findings(
        ["docs/aide/progress.md", "src/a.py"], authorised,
        always=("docs/aide/progress.md",))
    assert unauthorised == []


def test_findings_empty_diff_is_clean():
    assert aide.scope_findings([], aide.AuthorisedPaths(["src/a.py"], [])) == ([], [])


# --------------------------------------------------------------------------- #
# end to end
# --------------------------------------------------------------------------- #
def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "Tester"], path)
    (path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    items = path / "docs" / "aide" / "items"
    items.mkdir(parents=True)
    (items / "042-demo-item.md").write_text(SPEC, encoding="utf-8")
    (path / "src" / "demo").mkdir(parents=True)
    (path / "src" / "demo" / "rules.py").write_text("x = 1\n", encoding="utf-8")
    (path / "tests" / "golden").mkdir(parents=True)
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)
    return path


def _write(path: Path, rel: str, text: str) -> None:
    target = path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_scope_ok_when_every_change_is_authorised(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "src/demo/rules.py", "x = 2\n")
    _write(repo, "tests/golden/case.json", "{}\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_scope_flags_a_file_outside_the_list(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "src/demo/other.py", "y = 1\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 1
    assert "src/demo/other.py not authorised" in capsys.readouterr().out


def test_scope_flags_changing_a_path_it_declared_as_pinned(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "docs/aide/catalogue.json", "{}\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 1
    assert "Asserts against" in capsys.readouterr().out


def test_scope_authorises_the_bookkeeping_files_and_the_spec_itself(tmp_path: Path):
    """progress.md, insights.md and the item's own spec are written on every
    item by the CLI and the roles, so no spec should have to list them."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "docs/aide/progress.md", "# p\n")
    _write(repo, "docs/aide/insights.md", "# i\n")
    _write(repo, "docs/aide/items/042-demo-item.md", SPEC + "\n## Decisions\n\nx\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    assert aide.main(["--repo", str(repo), "scope"]) == 0


def test_scope_checks_a_spec_that_only_pins(tmp_path: Path, capsys):
    """A stage-validation item changes only the bookkeeping every item may
    write, while pinning the tree it validates. That is checkable — and stricter
    than bailing out, since an accidental source edit is then caught."""
    repo = _init_repo(tmp_path / "repo")
    _write(repo, "docs/aide/items/042-demo-item.md",
           "# Item 042 — Demo\n\n## Authorised paths\n\n"
           "**Asserts against:**\n\n- `src/demo/rules.py` — pinned\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "asserts-only spec"], repo)
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "docs/aide/progress.md", "# p\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "bookkeeping only"], repo)

    assert aide.main(["--repo", str(repo), "scope"]) == 0

    _write(repo, "src/demo/rules.py", "x = 9\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "touches what it pinned"], repo)
    assert aide.main(["--repo", str(repo), "scope"]) == 1
    assert "Asserts against" in capsys.readouterr().out


def test_scope_reports_a_missing_section_rather_than_passing(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _write(repo, "docs/aide/items/042-demo-item.md", "# Item 042 — Demo\n\n## Description\n\nx\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "drop section"], repo)
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "src/demo/anything.py", "z = 1\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 2
    assert "never passed silently" in capsys.readouterr().err


def test_scope_skips_a_queue_branch(tmp_path: Path, capsys):
    """A queue branch legitimately aggregates many items' authorised paths, and
    resolves to no item — the pre-1.5.0 unanchored parse read `aide/queue-016`
    as item 016 and hard-errored on an unrelated spec."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-016"], repo)
    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 0
    assert "queue branch" in capsys.readouterr().out


def test_scope_cannot_guess_the_item_off_an_unrecognised_branch(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "spike/whatever"], repo)
    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 2
    assert "aide scope NNN" in capsys.readouterr().err


def test_scope_explicit_number_overrides_the_branch(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "spike/whatever"], repo)
    _write(repo, "src/demo/rules.py", "x = 3\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    assert aide.main(["--repo", str(repo), "scope", "42"]) == 0


def test_scope_uses_merge_base_not_the_branch_tip(tmp_path: Path):
    """A commit landing on the base branch after this branch forked is not this
    branch's change, and a two-dot diff against the tip would report it."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/042-demo-item"], repo)
    _write(repo, "src/demo/rules.py", "x = 2\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "work"], repo)

    _run(["git", "switch", "main"], repo)
    _write(repo, "unrelated/elsewhere.py", "q = 1\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "someone else's work"], repo)
    _run(["git", "switch", "aide/042-demo-item"], repo)

    assert aide.main(["--repo", str(repo), "scope", "--base", "main"]) == 0


def test_scope_missing_spec_is_an_error(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/099-nonexistent"], repo)
    rc = aide.main(["--repo", str(repo), "scope"])
    assert rc == 2
    assert "no spec for item 099" in capsys.readouterr().err
