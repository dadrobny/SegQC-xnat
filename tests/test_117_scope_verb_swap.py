"""Tests for item 117 -- retire the project-local scope-check script in favour
of the framework verb ``aide scope``.

Covers AC1-AC9, AC12, AC16-AC18. AC10/AC11 (the shape of
``tests/test_107_item_scope_check.py`` after the split) and AC13-AC15 (the
``tests/test_115_stage26_validation.py`` retarget) are asserted by the edits
to those two modules directly, not here.

This module is written against the item's *target* state and is expected to
be red until the builder lands the deletion/retarget -- the script still
exists and the CI job still calls it as this module is written. The one
partial exception is AC16/AC17: those exercise the framework verb, which
already exists (engine 1.14.0), so they are expected to pass already.

AC2's sweep deliberately does not walk ``docs/aide/**`` -- those documents
(item 107/110/115/116, queue-016) name the retired script as *provenance* and
must survive untouched (item 117's Not-in-scope). It also excludes
``tests/test_107_item_scope_check.py`` by name: that module's own surviving
AC12 tests legitimately quote the retired script's literal filename as the
string they search item 107's spec and queue-016 for -- the same kind of
provenance reference, just implemented as a doc-content assertion rather than
prose. And it excludes *this* module, whose own source necessarily
constructs the search token to look for.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_THIS_FILE = Path(__file__).resolve()
_SCRIPT = _REPO_ROOT / "scripts" / "check_item_scope.py"
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_INSIGHTS_MD = _REPO_ROOT / "docs" / "aide" / "insights.md"
_INSIGHTS_ARCHIVE_DIR = _REPO_ROOT / "docs" / "aide" / "insights"


def _captured_insight_lines() -> list:
    """Every captured insight line, live inbox and archives alike.

    A closed entry does not stay in `insights.md`: `aide insights archive`
    moves it, verbatim and immutable, into `insights/archive-YYYY-QN.md`.
    Reading only the live file would therefore make these assertions fail on
    the day the entries below are archived -- a housekeeping action, not a
    regression -- which is the defect class `test_114`'s AC8 notes already
    describe: pinning what the loop's own verbs are designed to move. The
    claim is what must survive unrewritten; which of the two files holds it
    is not part of the contract.
    """
    lines = _INSIGHTS_MD.read_text(encoding="utf-8").splitlines()
    if _INSIGHTS_ARCHIVE_DIR.is_dir():
        for archive in sorted(_INSIGHTS_ARCHIVE_DIR.glob("archive-*.md")):
            lines.extend(archive.read_text(encoding="utf-8").splitlines())
    return lines
_ITEM_117_SPEC = _REPO_ROOT / "docs" / "aide" / "items" / "117-retire-check-item-scope-script.md"

# Excluded from AC2's sweep -- see module docstring.
_AC2_EXCLUDED_NAMES = ("test_107_item_scope_check.py", _THIS_FILE.name)

_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"


def _load_aide():
    spec = importlib.util.spec_from_file_location("_aide_cli_117", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# AC1: the script is gone; its siblings are not.
# --------------------------------------------------------------------------- #


def test_ac1_script_is_deleted():
    assert not _SCRIPT.exists(), f"{_SCRIPT} should have been deleted"


def test_ac1_sibling_scripts_survive():
    for name in ("aide_status_report.py", "refresh_reference.py"):
        sibling = _REPO_ROOT / "scripts" / name
        assert sibling.exists(), f"{sibling} should still exist"


# --------------------------------------------------------------------------- #
# AC2: no executable reference to the retired script survives.
# --------------------------------------------------------------------------- #

# Built by concatenation, deliberately, so this module's own source does not
# contain the contiguous literal it searches for.
_RETIRED_SCRIPT_TOKEN = "check_item" + "_scope"

_AC2_SWEPT_DIRS = ("tests", ".github", "scripts")
_AC2_SUFFIXES = (".py", ".yml", ".yaml", ".md")


def _ac2_candidate_files():
    for dirname in _AC2_SWEPT_DIRS:
        root = _REPO_ROOT / dirname
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix not in _AC2_SUFFIXES:
                continue
            if path.name in _AC2_EXCLUDED_NAMES:
                continue
            yield path


def test_ac2_no_executable_reference_to_the_retired_script_survives():
    candidates = list(_ac2_candidate_files())
    assert candidates, "expected at least one .py/.yml/.md file under tests/, .github/, scripts/"
    hits = []
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        if _RETIRED_SCRIPT_TOKEN in text:
            hits.append(path.relative_to(_REPO_ROOT).as_posix())
    assert not hits, f"stale reference(s) to the retired script found in: {hits}"


# --------------------------------------------------------------------------- #
# AC3: CLAUDE.md no longer names it.
# --------------------------------------------------------------------------- #


def test_ac3_claude_md_does_not_name_the_retired_script():
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    assert _RETIRED_SCRIPT_TOKEN not in text


# --------------------------------------------------------------------------- #
# AC4: both insight entries are ticked in place, append-only.
# --------------------------------------------------------------------------- #


def test_ac4_path_matches_insight_is_ticked_and_pointed_at_117():
    lines = _captured_insight_lines()
    # Locate by a distinctive substring of the *captured* claim text, not by
    # a hardcoded whole-line literal -- the line must survive unrewritten.
    needle = "does not support a mid/end single-star glob"
    matches = [ln for ln in lines if needle in ln]
    assert matches, f"expected a captured insight line containing {needle!r}"
    assert len(matches) == 1, f"expected exactly one match, found {len(matches)}"
    line = matches[0]
    assert line.startswith("- [x]"), f"entry not ticked: {line[:80]!r}..."
    assert "→" in line, f"entry has no pointer arrow: {line[:80]!r}..."
    assert "117" in line, f"entry does not name item 117: {line[:80]!r}..."
    # Append-only: the original captured claim text must still be present.
    assert needle in line


def test_ac4_stale_base_main_insight_is_ticked_and_pointed_at_117():
    lines = _captured_insight_lines()
    needle = "is stale on this checkout"
    matches = [ln for ln in lines if needle in ln]
    assert matches, f"expected a captured insight line containing {needle!r}"
    assert len(matches) == 1, f"expected exactly one match, found {len(matches)}"
    line = matches[0]
    assert line.startswith("- [x]"), f"entry not ticked: {line[:80]!r}..."
    assert "→" in line, f"entry has no pointer arrow: {line[:80]!r}..."
    assert "117" in line, f"entry does not name item 117: {line[:80]!r}..."
    assert needle in line


# --------------------------------------------------------------------------- #
# AC5-AC9: the retargeted `scope-check` CI job's shape.
# --------------------------------------------------------------------------- #

_JOB_KEY_RE = re.compile(r"^  [A-Za-z0-9_-]+:\s*$")


def _scope_check_job_text() -> str:
    text = _CI_YML.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line == "  scope-check:":
            start = i
            break
    assert start is not None, "no 'scope-check:' job found in ci.yml"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _JOB_KEY_RE.match(lines[i]):
            end = i
            break
    job_text = "\n".join(lines[start:end])
    assert job_text.strip(), "scope-check job text unexpectedly empty"
    return job_text


def test_ac5_ci_resolves_an_item_number_with_the_anchored_expression():
    job = _scope_check_job_text()
    assert r"s|^aide/\([0-9]\{3\}\)-.*|\1|p" in job
    assert "docs/aide/items/" not in job


def test_ac6_ci_invokes_the_scope_verb_with_an_origin_base():
    job = _scope_check_job_text()
    assert ".aide/scripts/aide.py scope" in job
    assert '--base "origin/' in job


def test_ac7_ci_always_passes_a_positional_item_number():
    job = _scope_check_job_text()
    lines = [ln for ln in job.splitlines() if ".aide/scripts/aide.py scope" in ln]
    assert lines, "no line invokes '.aide/scripts/aide.py scope'"
    for line in lines:
        after = line.split(".aide/scripts/aide.py scope", 1)[1].strip()
        assert after, "the scope invocation has no argument after the verb"
        assert not after.startswith("--"), (
            f"expected a positional item number, found a flag first: {after!r}"
        )


def test_ac8_ci_keeps_full_history():
    job = _scope_check_job_text()
    assert "fetch-depth: 0" in job


def test_ac9_ci_pins_a_python_with_tomllib():
    job = _scope_check_job_text()
    assert "setup-python" in job, "no actions/setup-python step in the scope-check job"
    versions = re.findall(r'python-version:\s*["\']?(\d+)\.(\d+)', job)
    assert versions, "no python-version pinned in the scope-check job"
    major, minor = (int(v) for v in versions[0])
    assert (major, minor) >= (3, 11), f"pinned Python {major}.{minor} lacks tomllib"


# --------------------------------------------------------------------------- #
# AC12: no orphaned helper or import left in test_107.
# --------------------------------------------------------------------------- #


def test_ac12_test_107_defines_no_orphaned_helpers():
    module = _TESTS_DIR / "test_107_item_scope_check.py"
    text = module.read_text(encoding="utf-8")
    for name in (
        "_SCRIPT", "_STDLIB_FALLBACK", "_git", "_init_repo", "_write",
        "_commit", "_write_spec", "_run_checker",
    ):
        assert name not in text, f"orphaned {name!r} still present in {module.name}"


def test_ac12_test_107_imports_no_orphaned_module():
    module = _TESTS_DIR / "test_107_item_scope_check.py"
    tree_text = module.read_text(encoding="utf-8")
    tree = ast.parse(tree_text, filename=str(module))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    for name in ("ast", "subprocess", "sys", "pytest"):
        assert name not in imported, f"orphaned import {name!r} still present in {module.name}"


# --------------------------------------------------------------------------- #
# AC16/AC17: live parity pair -- the surviving checker still has teeth, and
# still passes a clean branch. Built as a throwaway repo under tmp_path, the
# way `.aide/scripts/tests/test_aide_scope.py` does, and driven in-process
# via `aide.main` (never a subprocess parsing stdout -- .aide/conventions.md
# §6, and the recorded Windows `stdout is None` failure mode).
# --------------------------------------------------------------------------- #

_SYNTH_AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"

[git]
mode = "local"
main_branch = "main"
branch_prefix = "aide/"
"""

_SYNTH_SPEC = """\
# Item 042 -- Demo item

## Description

Something.

## Authorised paths

**May change:**

- `src/demo/rules.py` -- the new rule
"""

_SYNTH_SPEC_NO_SECTION = """\
# Item 042 -- Demo item

## Description

Something, with no Authorised paths section at all.
"""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=30,
    )


def _init_synth_repo(tmp_path: Path, spec_text: str = _SYNTH_SPEC) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test-117@example.com")
    _git(repo, "config", "user.name", "Test 117")
    (repo / "aide.toml").write_text(_SYNTH_AIDE_TOML, encoding="utf-8")
    items = repo / "docs" / "aide" / "items"
    items.mkdir(parents=True)
    (items / "042-demo-item.md").write_text(spec_text, encoding="utf-8")
    (repo / "src" / "demo").mkdir(parents=True)
    (repo / "src" / "demo" / "rules.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _run_scope(aide_module, repo: Path) -> int:
    return aide_module.main(["--repo", str(repo), "scope", "42", "--base", "main"])


def test_ac16_violation_outside_may_change_makes_scope_exit_1(tmp_path, capsys):
    aide_module = _load_aide()
    repo = _init_synth_repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "feature")
    outside = repo / "outside.txt"
    outside.write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "out of scope change")

    rc = _run_scope(aide_module, repo)
    out = capsys.readouterr().out
    assert out.strip(), "expected non-empty stdout from a violating scope check"

    assert rc == 1
    assert "outside.txt" in out


def test_ac17_fully_authorised_branch_makes_scope_exit_0(tmp_path, capsys):
    aide_module = _load_aide()
    repo = _init_synth_repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "feature")
    rules = repo / "src" / "demo" / "rules.py"
    rules.write_text("x = 2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "in scope change")

    rc = _run_scope(aide_module, repo)
    out = capsys.readouterr().out
    assert out.strip(), "expected non-empty stdout from a clean scope check"

    assert rc == 0


# --------------------------------------------------------------------------- #
# Adversarial / edge cases
# --------------------------------------------------------------------------- #


def test_adv_synthetic_repo_tests_never_touch_the_real_repo(tmp_path):
    """The throwaway repo lives entirely under tmp_path; nothing in this
    module's helpers writes into the real checkout."""
    repo = _init_synth_repo(tmp_path)
    assert repo.is_relative_to(tmp_path)
    assert repo != _REPO_ROOT
    assert not repo.is_relative_to(_REPO_ROOT)


def test_adv_missing_authorised_paths_section_exits_2_not_0(tmp_path, capsys):
    aide_module = _load_aide()
    repo = _init_synth_repo(tmp_path, spec_text=_SYNTH_SPEC_NO_SECTION)
    _git(repo, "switch", "-q", "-c", "feature")
    (repo / "src" / "demo" / "rules.py").write_text("x = 2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")

    rc = _run_scope(aide_module, repo)
    err = capsys.readouterr().err
    assert err.strip(), "expected a non-empty error message for a missing section"

    assert rc == 2
    assert rc != 0


def test_adv_zero_commits_beyond_base_exits_0(tmp_path, capsys):
    aide_module = _load_aide()
    repo = _init_synth_repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "feature")  # no further commits

    rc = _run_scope(aide_module, repo)
    out = capsys.readouterr().out
    assert out.strip(), "expected a non-empty status message from a no-op scope check"

    assert rc == 0


# --------------------------------------------------------------------------- #
# AC18: the parity run is recorded in this spec's own Decisions log.
# --------------------------------------------------------------------------- #


def test_ac18_parity_check_entry_recorded_in_decisions_log():
    text = _ITEM_117_SPEC.read_text(encoding="utf-8")
    marker = "## Decisions & Trade-offs"
    assert marker in text, f"no {marker!r} heading found in {_ITEM_117_SPEC.name}"
    decisions = text.split(marker, 1)[1]
    assert decisions.strip(), "Decisions & Trade-offs section is empty"

    assert "Parity check" in decisions, (
        "expected a dated 'Parity check' entry recording the pre-deletion "
        "head-to-head run"
    )
    assert _RETIRED_SCRIPT_TOKEN in decisions, (
        "Parity check entry does not name the retired script"
    )
    assert ".aide/scripts/aide.py" in decisions, (
        "Parity check entry does not name the framework verb"
    )
    # Both checkers' exit codes for both a known-violating and a known-clean
    # state -- looked for as "exit <digit>", tolerant of exact phrasing.
    exit_codes = re.findall(r"exit `?\d", decisions)
    assert len(exit_codes) >= 2, (
        f"expected at least two reported exit codes in the Parity check "
        f"entry, found {len(exit_codes)}"
    )


# --------------------------------------------------------------------------- #
# AC19: the retired coverage is replaced, not merely relocated.
#
# AC10 removed 17 tests that exercised the deleted script's behaviour. Of this
# module's own tests only four exercise the verb (AC16, AC17 and two
# adversarial cases); the rest are structural. The real replacement is the
# framework's `.aide/scripts/tests/test_aide_scope.py`, which `testpaths =
# ["tests"]` did not collect -- so a bare `python -m pytest` would have gone
# from 17 behavioural tests over the scope check to four while this item
# claimed a like-for-like swap. Collecting the framework suite is what makes
# the claim true, so it is pinned here rather than left to convention.
# --------------------------------------------------------------------------- #

_FRAMEWORK_TESTS_PATH = ".aide/scripts/tests"


def test_ac19_testpaths_collects_the_framework_suite():
    pyproject = _REPO_ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    marker = "[tool.pytest.ini_options]"
    assert marker in text, "pyproject.toml has no pytest configuration section"
    section = text.split(marker, 1)[1]
    testpaths_lines = [
        line for line in section.splitlines() if line.strip().startswith("testpaths")
    ]
    assert testpaths_lines, "pytest configuration declares no testpaths"

    assert _FRAMEWORK_TESTS_PATH in testpaths_lines[0], (
        f"testpaths must include {_FRAMEWORK_TESTS_PATH!r} -- it is the only "
        f"live coverage of the scope verb this item swapped to; got "
        f"{testpaths_lines[0]!r}"
    )


def test_ac19_the_framework_scope_suite_actually_exists_and_has_tests():
    """A path in `testpaths` proves nothing if it holds no scope tests.

    The AC is about coverage, not configuration, so assert the file is there
    and defines a recognisable number of tests before believing the entry
    above means anything.
    """
    suite = _REPO_ROOT / _FRAMEWORK_TESTS_PATH / "test_aide_scope.py"
    assert suite.is_file(), f"{_FRAMEWORK_TESTS_PATH}/test_aide_scope.py is missing"

    tree = ast.parse(suite.read_text(encoding="utf-8"))
    test_functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    assert len(test_functions) >= 20, (
        f"expected the framework scope suite to carry substantive coverage; "
        f"found only {len(test_functions)} test function(s)"
    )
