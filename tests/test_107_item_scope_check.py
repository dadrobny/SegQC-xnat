"""Tests for item 107's ``scripts/check_item_scope.py`` diff-based scope check.

Per the item spec's Assumptions ("The check belongs to the branch, never to
pytest") this module tests the **script itself** as an external process over
synthetic git repositories built fresh under ``tmp_path`` -- it never asserts
anything about *this* repo's scope (that is the CI job's / validator's job,
AC11/AC12). AC1/AC2/AC3/AC13 are the exception: they are repo-state
assertions about the fence removal (an absence, not a byte-identity), written
grep-style over ``tests/`` source text, matching the pattern the item's own
``test_106_stage19_validation.py`` uses for its own non-fence structural
checks.

The script does not exist until the builder lands it. Every test below is a
real, currently-failing assertion against ``scripts/check_item_scope.py`` --
none are skipped -- so this module goes green exactly when AC5-AC10 land.

Conventions asserted about the script's CLI, inferred from the spec's
Implementation Steps and Validation section (`python scripts/check_item_scope.py
docs/aide/items/107-*.md`) since no ACs pin exact flag spelling:

- positional argument: path to the item spec markdown file.
- ``--base <ref>``: overrides the base ref (default ``main``), per the
  Assumptions section ("Base ref defaults to main, overridable by argument").
- exit 0 clean, 1 on a violation, 2 on a missing/empty ``## Authorised
  paths`` section (spec's own Implementation Step 5).

All temporary repos get an explicit local git identity and an explicit
initial branch name (``git init -b main``) so these tests do not depend on
any global git config on the host or CI runner. All path comparisons use
``Path.relative_to(...).as_posix()`` -- never ``str(Path)`` -- so the
POSIX-style paths this test module writes into spec files match what the
script reports on Windows too.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_item_scope.py"

_STDLIB_FALLBACK = {
    "__future__", "argparse", "ast", "collections", "dataclasses", "fnmatch",
    "functools", "io", "itertools", "json", "os", "pathlib", "re", "shlex",
    "shutil", "subprocess", "sys", "textwrap", "typing",
}


# --------------------------------------------------------------------------- #
# Helpers: synthetic git repos under tmp_path, never the real repo.
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=test-107@example.com", "-c", "user.name=Test 107", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _write(repo: Path, relpath: str, content: str = "content\n") -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _commit(repo: Path, message: str = "commit") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _write_spec(repo: Path, authorised, *, section: bool = True, name: str = "spec.md") -> Path:
    """Write a synthetic item spec with (or without) an Authorised paths section.

    ``authorised`` is a list of glob strings, or ``None``/``[]`` for an empty
    section body. Bullets are backtick-fenced, matching this item's own
    ``107-retire-byte-hash-scope-fences.md``.
    """
    lines = ["# Synthetic item spec\n", "\n## Description\n\nSynthetic.\n\n"]
    if section:
        lines.append("## Authorised paths\n\n")
        for entry in authorised or []:
            lines.append(f"- `{entry}`\n")
        lines.append("\n## Decisions & Trade-offs\n\nNone.\n")
    spec = repo / name
    spec.write_text("".join(lines), encoding="utf-8")
    return spec


def _run_checker(spec: Path, cwd: Path, base: str | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(_SCRIPT), str(spec)]
    if base is not None:
        args += ["--base", base]
    return subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, timeout=30,
    )


def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


# --------------------------------------------------------------------------- #
# AC5: the checker exists and is stdlib-only.
# --------------------------------------------------------------------------- #


def test_ac5_script_exists_and_imports_only_stdlib():
    assert _SCRIPT.exists(), f"{_SCRIPT} does not exist yet"
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    top_level = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top_level.add(node.module.split(".")[0])
    allowed = set(getattr(sys, "stdlib_module_names", _STDLIB_FALLBACK))
    disallowed = top_level - allowed
    assert not disallowed, f"non-stdlib top-level imports found: {sorted(disallowed)}"


# --------------------------------------------------------------------------- #
# AC6: flags an out-of-scope change.
# --------------------------------------------------------------------------- #


def test_ac6_out_of_scope_change_is_flagged(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/a.txt", "v1\n")
    _write(repo, "outside.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/a.txt", "v2\n")
    _write(repo, "outside.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert "outside.txt" in result.stdout


# --------------------------------------------------------------------------- #
# AC7: passes an in-scope change.
# --------------------------------------------------------------------------- #


def test_ac7_fully_in_scope_change_exits_zero(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/a.txt", "v1\n")
    _write(repo, "outside.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/a.txt", "v2\n")
    _write(repo, "outside.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**", "outside.txt"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# AC8: a missing/empty section is an error, not a pass.
# --------------------------------------------------------------------------- #


def test_ac8_missing_authorised_paths_section_is_an_error(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "a.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, None, section=False)

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert spec.name in result.stdout + result.stderr


def test_ac8_empty_authorised_paths_section_is_an_error(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "a.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, [])  # section present, zero bullets

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert spec.name in result.stdout + result.stderr


def test_ac8_missing_and_empty_section_both_exit_two(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "a.txt", "v2\n")
    _commit(repo, "feature work")
    missing = _write_spec(repo, None, section=False, name="missing.md")
    empty = _write_spec(repo, [], name="empty.md")

    assert _run_checker(missing, cwd=repo).returncode == 2
    assert _run_checker(empty, cwd=repo).returncode == 2


# --------------------------------------------------------------------------- #
# AC9: the diff is computed against the merge base, not the base branch's
# current tip.
# --------------------------------------------------------------------------- #


def test_ac9_commit_landing_on_base_after_branching_is_not_misreported(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "keep.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "keep.txt", "v2\n")
    _commit(repo, "feature work")
    # Land a commit on main *after* feature branched, touching a file feature
    # never sees -- a two-dot / tip-of-base diff would misreport this as
    # changed; a merge-base diff must not.
    _git(repo, "checkout", "-q", "main")
    _write(repo, "main_only.txt", "landed after branch\n")
    _commit(repo, "post-branch main commit")
    _git(repo, "checkout", "-q", "feature")
    spec = _write_spec(repo, ["keep.txt"])

    result = _run_checker(spec, cwd=repo, base="main")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "main_only.txt" not in result.stdout


# --------------------------------------------------------------------------- #
# AC10: glob semantics -- one test per form.
# --------------------------------------------------------------------------- #


def test_ac10_exact_path_matches_only_itself(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "keep.txt", "v1\n")
    _write(repo, "notes/keep.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "keep.txt", "v2\n")
    _write(repo, "notes/keep.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["keep.txt"])  # exact entry, no wildcard

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    lines = result.stdout.splitlines()
    assert any(line.startswith("notes/keep.txt") for line in lines)
    # The exact entry "keep.txt" must not also be reported as a violation --
    # only its unrelated same-named sibling under notes/ should be.
    assert not any(line.startswith("keep.txt ") for line in lines)


def test_ac10_dir_star_star_matches_depth_one(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/a.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_ac10_dir_star_star_matches_depth_three(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/sub/deep/b.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/sub/deep/b.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_ac10_dir_star_star_does_not_match_sibling_directory(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/a.txt", "v1\n")
    _write(repo, "dir_other/x.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/a.txt", "v2\n")
    _write(repo, "dir_other/x.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert "dir_other/x.txt" in result.stdout


# --------------------------------------------------------------------------- #
# Adversarial: glob matching nothing, unusual characters, zero-change branch,
# detached HEAD, non-existent base ref.
# --------------------------------------------------------------------------- #


def test_adv_glob_matching_nothing_does_not_suppress_real_violation(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "outside.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "outside.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["this/glob/matches/nothing/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert "outside.txt" in result.stdout


def test_adv_unusual_characters_in_changed_path_are_handled(tmp_path):
    repo = _init_repo(tmp_path)
    weird = "dir/weird file (v1) [draft].txt"
    _write(repo, weird, "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, weird, "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_adv_unusual_characters_in_unauthorised_path_are_named(tmp_path):
    repo = _init_repo(tmp_path)
    weird = "weird file (v1) [draft].txt"
    _write(repo, weird, "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, weird, "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["dir/**"])  # does not cover the weird path

    result = _run_checker(spec, cwd=repo)

    assert result.returncode != 0
    assert weird in result.stdout


def test_adv_branch_with_zero_changes_exits_zero(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")  # no further commits
    spec = _write_spec(repo, ["a.txt"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_adv_detached_head_is_handled(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "dir/a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "dir/a.txt", "v2\n")
    _commit(repo, "feature work")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", sha)  # detached HEAD
    spec = _write_spec(repo, ["dir/**"])

    result = _run_checker(spec, cwd=repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_adv_nonexistent_base_ref_is_a_clear_nonzero_error(tmp_path):
    repo = _init_repo(tmp_path)
    _write(repo, "a.txt", "v1\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "a.txt", "v2\n")
    _commit(repo, "feature work")
    spec = _write_spec(repo, ["a.txt"])

    result = _run_checker(spec, cwd=repo, base="does-not-exist-branch")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert combined.strip(), "expected a non-empty error message"
    assert "does-not-exist-branch" in combined


# --------------------------------------------------------------------------- #
# AC1/AC2/AC3: repo-state assertions about the fence removal. Grep-style,
# like test_106_stage19_validation.py's own non-fence structural checks --
# these pin an absence, not a byte-identity, and self-heal if a later item
# legitimately needs a `_PRE_` constant again.
# --------------------------------------------------------------------------- #

_FENCE_ITEM_NUMBERS = ("099", "100", "101", "103", "105")
_FENCE_PATTERN = re.compile(r"_PRE_(" + "|".join(_FENCE_ITEM_NUMBERS) + r")_")


def _all_test_sources() -> dict:
    return {p: p.read_text(encoding="utf-8") for p in sorted(_TESTS_DIR.glob("*.py"))}


def test_ac1_no_pre_099_100_101_103_105_fence_constant_remains_under_tests():
    hits = []
    for path, text in _all_test_sources().items():
        for match in _FENCE_PATTERN.finditer(text):
            hits.append(f"{_rel(path, _REPO_ROOT)}: {match.group(0)}")
    assert not hits, f"fence identifiers still present: {hits}"


def test_ac2_pre_106_row_digest_constants_removed_from_test_106():
    test_106 = _TESTS_DIR / "test_106_stage19_validation.py"
    text = test_106.read_text(encoding="utf-8")
    for name in (
        "_PRE_106_OBJECTIVE_ROW_DIGESTS",
        "_PRE_106_OUTCOME_TARGETS_DIGEST",
        "_PRE_106_REAL_CORPUS_ROW_DIGEST",
    ):
        assert name not in text, f"{name} still present in {test_106.name}"


def test_ac2_pre_106_consuming_tests_removed_from_test_106():
    test_106 = _TESTS_DIR / "test_106_stage19_validation.py"
    text = test_106.read_text(encoding="utf-8")
    for func_name in (
        "test_ac24_objective_coverage_g7_and_g8_rows_unchanged",
        "test_ac24_outcome_targets_table_unchanged",
        "test_ac24_real_corpus_verification_row_unchanged_and_names_stage16",
    ):
        assert f"def {func_name}(" not in text, f"{func_name} still defined in {test_106.name}"


def test_ac3_no_combined_hash_or_tracked_files_helper_remains_in_fence_modules():
    for number in _FENCE_ITEM_NUMBERS:
        matches = sorted(_TESTS_DIR.glob(f"test_{number}_*.py"))
        assert matches, f"expected a test_{number}_*.py module to still exist"
        for path in matches:
            text = path.read_text(encoding="utf-8")
            assert "def _combined_hash(" not in text, f"orphaned _combined_hash in {path.name}"
            assert "def _tracked_files(" not in text, f"orphaned _tracked_files in {path.name}"


# --------------------------------------------------------------------------- #
# AC11: CI runs the check on pull requests.
# --------------------------------------------------------------------------- #


def test_ac11_ci_workflow_runs_the_checker_on_pull_requests():
    ci_yml = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_yml.read_text(encoding="utf-8")
    assert "pull_request" in text
    assert "check_item_scope.py" in text


def test_ac11_ci_workflow_scope_job_uses_the_pr_base_ref():
    ci_yml = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_yml.read_text(encoding="utf-8")
    assert "base_ref" in text


# --------------------------------------------------------------------------- #
# AC12: the validator is obliged to run it -- discoverable from the item
# spec and the queue, not folklore.
# --------------------------------------------------------------------------- #


def test_ac12_item_107_spec_documents_the_authorised_paths_convention():
    spec = _REPO_ROOT / "docs" / "aide" / "items" / "107-retire-byte-hash-scope-fences.md"
    text = spec.read_text(encoding="utf-8")
    assert "## Authorised paths" in text
    assert "check_item_scope.py" in text


def test_ac12_queue_016_references_the_scope_check_command():
    queue = _REPO_ROOT / "docs" / "aide" / "queue" / "queue-016.md"
    text = queue.read_text(encoding="utf-8")
    assert "check_item_scope.py" in text
    assert "Authorised paths" in text


# --------------------------------------------------------------------------- #
# AC13: non-fence byte comparisons survive -- named-presence checks, since
# this module may not run pytest itself; the full-suite pass is confirmed
# separately by the validator.
# --------------------------------------------------------------------------- #


def test_ac13_intra_run_determinism_test_still_present():
    module = _TESTS_DIR / "test_042_golden_determinism.py"
    text = module.read_text(encoding="utf-8")
    assert "def test_ac4_two_successive_runs_are_byte_identical(" in text


def test_ac13_item_104_drift_tests_still_present():
    module = _TESTS_DIR / "test_104_feature_catalogue_drift.py"
    text = module.read_text(encoding="utf-8")
    assert "def test_ac8_direction1_clean_on_current_tree(" in text
    assert "def test_ac9_direction2_clean_on_current_tree(" in text


def test_ac13_item_098_expected_value_baselines_still_present():
    module = _TESTS_DIR / "test_098_stray_components.py"
    text = module.read_text(encoding="utf-8")
    assert "def test_ac12_hand_set_fragmentation_findings_match_frozen_snapshot(" in text
    assert "def test_ac13_reference_derived_excess_finding_matches_frozen_snapshot(" in text
    assert "def test_ac15_golden_verdict_and_findings_unchanged(" in text
