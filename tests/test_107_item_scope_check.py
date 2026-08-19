"""Item 107's fence-retirement regression tests, plus CI-job assertions.

Item 117 retired this module's other half: the 17 tests that exercised this
repo's project-local scope-check script as an external process over
synthetic git repositories. That script is gone -- its diff-time scope check
now lives in the framework verb ``aide scope`` (``.aide/scripts/aide.py``),
whose own unit suite (``.aide/scripts/tests/test_aide_scope.py``, not
collected by this repo's ``testpaths``) covers it; item 117's
``tests/test_117_scope_verb_swap.py`` carries the project-side parity
assertions (AC16/AC17) that used to live here.

What remains is item 107's original *fence-retirement* half: AC1/AC2/AC3
assert (grep-style, over ``tests/`` source text) that the byte-hash
``_PRE_NNN_*`` scope fences item 107 replaced are gone and stay gone --
matching the pattern ``test_106_stage19_validation.py`` uses for its own
non-fence structural checks. AC11/AC12/AC13 assert the surrounding
bookkeeping: the CI job runs some scope check on pull requests (AC11,
retargeted by item 117 at the new command), item 107's spec and queue-016
document the convention as provenance (AC12), and the other item-098/104/042
determinism tests it retired the fences in favour of are still present
(AC13).
"""

from __future__ import annotations

import re
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent


def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


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
    # Retargeted by item 117 (AC6): the job now invokes the framework verb
    # rather than the deleted project script.
    assert ".aide/scripts/aide.py scope" in text


def test_ac11_ci_workflow_scope_job_uses_the_pr_base_ref():
    ci_yml = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_yml.read_text(encoding="utf-8")
    assert "base_ref" in text


# --------------------------------------------------------------------------- #
# AC12: the validator is obliged to run it -- discoverable from the item
# spec and the queue, not folklore.
#
# These two tests legitimately embed the retired script's literal filename as
# the string they search item 107's spec / queue-016 for -- that provenance
# text must never be rewritten (item 117's Not-in-scope). For exactly that
# reason item 117's own AC2 sweep (tests/test_117_scope_verb_swap.py)
# excludes this module by name, the same way it leaves docs/aide/** unswept.
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
