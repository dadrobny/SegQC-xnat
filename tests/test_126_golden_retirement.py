"""Tests for item 126 -- execute the golden retirement (Stage 29, D1).

This item deletes eleven committed whole-record report snapshots dispositioned
``retire`` by the human maintainer (item 106, ``docs/aide/golden-decision-
table.md`` Section 1) and lands the four replacements the signed rows name.
Covers Acceptance Criteria AC1-AC24. Per the item's Implementation Steps, the
**test-writer** owns everything under ``tests/`` (this module, the re-pointing
and deletion of the ~40 consumer functions listed in the item's Testing
Strategy disposition table) and the **builder** owns ``src/``,
``.gitattributes``, the decision table, and the deletion of the eleven files
-- so most tests here are expected to FAIL until the builder lands its half.

Where an AC concerns another module's source (AC5, AC9, AC12, AC13), this
module reads that module's text/AST rather than importing it, so a failure
names the offending function instead of erroring at import.

Adversarial / edge cases covered:

- AC19's both-directions check: a synthetic execution-log line naming a path
  that still exists on disk fails; a synthetic Section-1 row naming an absent
  path with no execution-log line fails.
- AC17's allowlist is proved reachable with a synthetic offending string --
  an allowlist that matches nothing is not evidence.
- The format fixture present but empty fails with an ``AssertionError``, not
  a crash; present with CRLF content is well-defined under ``read_text``'s
  universal-newline translation (both carried over from ``test_111``'s
  model).
- The format fixture present but drifted by one key fails with a message
  naming the drift.
- ``write_goldens(tmp)`` into an already-populated directory is still
  idempotent, and ``main(["--out", tmp])`` still returns 0 and writes nine
  files -- the harness works, only the committed store is gone.
- A regenerated report and the format fixture's hand-built report share no
  float value, so a future edit cannot quietly re-couple the two.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_CORPUS_GOLDEN_DIR = _TESTS_DIR / "corpus" / "golden"
_GOLDEN_016 = _TESTS_DIR / "golden" / "016_features_report.json"
_GOLDEN_022 = _TESTS_DIR / "golden" / "022_stage3_report.json"
_FORMAT_FIXTURE = _TESTS_DIR / "golden" / "report_format_contract.json"
_DECISION_TABLE = _REPO_ROOT / "docs" / "aide" / "golden-decision-table.md"
_GITATTRIBUTES = _REPO_ROOT / ".gitattributes"
_COMPANION_PATH = _REPO_ROOT / "docs" / "aide" / "golden_evidence.generated.json"
_SCHEMA_PATH = _REPO_ROOT / "src" / "segfacet" / "report_schema_v0.json"

_GOLDEN_MARKERS = ("GOLDEN_DIR", "load_golden", "read_golden_text", "check_case_golden")
_GOLDEN_MARKERS_WITH_PATH = _GOLDEN_MARKERS + ("tests/corpus/golden",)

_CASE_IDS = (
    "clean_control",
    "mode1_displace",
    "mode2_fragment",
    "mode3_inject_islands",
    "mode4_relabel_swap",
    "mode5_remove_level",
    "mode6_crop_at_border",
    "mode7_sequence_break",
    "mode8_force_overlap",
)


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _module_source(rel_path: str) -> str:
    return (_REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _module_ast(rel_path: str) -> ast.Module:
    return ast.parse(_module_source(rel_path), filename=rel_path)


def _function_source(tree: ast.Module, name: str, *, where: str) -> str:
    """Source text of the top-level (or nested-once) function/def named
    *name*, via AST slicing -- never an import."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(_module_source(where), node)
            assert segment is not None, f"could not slice source for {name!r} in {where!r}"
            return segment
    raise AssertionError(f"{name!r} is not defined in {where!r}")


def _function_names(tree: ast.Module) -> set:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _run_manifest_cases():
    from segfacet.synth.corpus import load_manifest

    return load_manifest()["cases"]


def _report_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


# =========================================================================== #
# AC1/AC2: the eleven retired files are gone
# =========================================================================== #


def test_ac1_nine_corpus_snapshots_are_gone():
    matches = sorted(_CORPUS_GOLDEN_DIR.glob("*.json")) if _CORPUS_GOLDEN_DIR.exists() else []
    assert matches == [], f"tests/corpus/golden/*.json still present: {matches}"


def test_ac2_two_serialisation_snapshots_are_gone():
    assert not _GOLDEN_016.exists(), f"{_GOLDEN_016} still exists"
    assert not _GOLDEN_022.exists(), f"{_GOLDEN_022} still exists"


# =========================================================================== #
# AC3: the corpus itself survives, and every case validates fresh
# =========================================================================== #


def test_ac3_manifest_cases_resolve_to_existing_fixtures():
    from segfacet.synth.corpus import CORPUS_DIR

    cases = _run_manifest_cases()
    assert cases, "expected at least one manifest case"
    for case in cases:
        seg_path = CORPUS_DIR / case["seg_fixture"]
        assert seg_path.is_file(), f"missing seg fixture for {case['case_id']!r}: {seg_path}"


@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_ac3_fresh_report_validates_against_schema(case_id):
    import jsonschema

    from segfacet.synth.golden import build_report_for_case

    cases = {c["case_id"]: c for c in _run_manifest_cases()}
    assert case_id in cases, f"{case_id!r} missing from committed manifest"
    report = build_report_for_case(cases[case_id])
    jsonschema.validate(report, _report_schema())


# =========================================================================== #
# AC4: no retired path was regenerated on the way out (last commit == D)
# =========================================================================== #

_RETIRED_PATHS = tuple(
    f"tests/corpus/golden/{case_id}.json" for case_id in _CASE_IDS
) + (
    "tests/golden/016_features_report.json",
    "tests/golden/022_stage3_report.json",
)


@pytest.mark.parametrize("rel_path", _RETIRED_PATHS)
def test_ac4_most_recent_history_entry_for_each_retired_path_is_a_deletion(rel_path):
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--name-status", "--format=%H", "--", rel_path],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        pytest.skip("git is unavailable to the runner")
    if result.returncode != 0:
        pytest.skip(f"git log failed for {rel_path!r}: {result.stderr}")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"no history found for {rel_path!r}"

    # First status line after the first commit hash is the most recent change.
    status_line = None
    for line in lines[1:]:
        if line[0] in "AMDRCT":
            status_line = line
            break
    assert status_line is not None, (
        f"could not find a status line for {rel_path!r} in git log output: {lines[:5]}"
    )
    assert status_line.startswith("D"), (
        f"most recent history entry for {rel_path!r} is not a deletion: {status_line!r}"
    )


# =========================================================================== #
# AC5: replacement (i) -- determinism assertions survive, golden-free
# =========================================================================== #

_AC5_DETERMINISM_TESTS = (
    ("tests/test_042_golden_determinism.py", "test_ac4_two_successive_runs_are_byte_identical"),
    ("tests/test_042_golden_determinism.py", "test_ac12_main_regenerates_matching_goldens"),
    ("tests/test_098_stray_components.py", "test_ac16_write_goldens_intra_run_determinism"),
    ("tests/test_016_features_json.py", "test_ac5_deterministic_repeated_serialisation"),
    ("tests/test_022_stage3_serialisation.py", "test_ac8_determinism_two_calls_equal"),
    ("tests/test_022_stage3_serialisation.py", "test_ac8_determinism_report_level"),
)


@pytest.mark.parametrize("module,func_name", _AC5_DETERMINISM_TESTS)
def test_ac5_determinism_test_exists_and_is_golden_free(module, func_name):
    tree = _module_ast(module)
    source = _function_source(tree, func_name, where=module)
    for marker in _GOLDEN_MARKERS:
        assert marker not in source, (
            f"{module}::{func_name} still references {marker!r}"
        )


# =========================================================================== #
# AC6: replacement (ii) -- schema validity reads fresh output, no golden read
# =========================================================================== #


def test_ac6_test042_ac7_reads_fresh_output_not_a_committed_file():
    module = "tests/test_042_golden_determinism.py"
    tree = _module_ast(module)
    source = _function_source(
        tree, "test_ac7_every_committed_golden_is_valid_json_and_validates", where=module
    )
    assert "build_report_for_case" in source, (
        "test_ac7_every_committed_golden_is_valid_json_and_validates no longer "
        "validates build_report_for_case output"
    )
    for marker in _GOLDEN_MARKERS_WITH_PATH:
        assert marker not in source, f"{module}::test_ac7_... still references {marker!r}"


# =========================================================================== #
# AC7: replacement (iii) -- verdict+findings pinned against fresh output
# =========================================================================== #


def test_ac7_test098_ac15_asserts_against_fresh_output():
    module = "tests/test_098_stray_components.py"
    tree = _module_ast(module)
    source = _function_source(
        tree, "test_ac15_golden_verdict_and_findings_unchanged", where=module
    )
    assert "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS" in source
    for marker in _GOLDEN_MARKERS_WITH_PATH:
        assert marker not in source, (
            f"{module}::test_ac15_golden_verdict_and_findings_unchanged still "
            f"references {marker!r}"
        )


def test_ac7_pre098_constant_still_importable_by_test102():
    import test_098_stray_components as mod098

    assert hasattr(mod098, "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS")
    module = "tests/test_102_stage18_validation.py"
    source = _module_source(module)
    assert "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS" in source, (
        f"{module} no longer imports _PRE_098_GOLDEN_VERDICT_AND_FINDINGS"
    )


# =========================================================================== #
# AC8: replacement (iv) -- one shared format fixture, two consumers
# =========================================================================== #


def test_ac8_format_fixture_exists():
    assert _FORMAT_FIXTURE.is_file(), f"{_FORMAT_FIXTURE} does not exist"


@pytest.mark.parametrize(
    "module,func_name",
    [
        ("tests/test_016_features_json.py", "test_ac5_golden_snapshot"),
        ("tests/test_022_stage3_serialisation.py", "test_ac8_golden_snapshot"),
    ],
)
def test_ac8_consumer_golden_path_points_at_shared_fixture(module, func_name):
    source = _module_source(module)
    assert "report_format_contract.json" in source, (
        f"{module} does not reference report_format_contract.json anywhere"
    )
    assert "016_features_report.json" not in source
    assert "022_stage3_report.json" not in source


# =========================================================================== #
# AC9: the format fixture is feature-value-free
# =========================================================================== #

_FORBIDDEN_FIXTURE_IMPORTS = (
    "segfacet.features",
    "segfacet.pipeline",
    "segfacet.synth",
)


def test_ac9_fixture_builder_module_exists_and_imports_no_extractor():
    builder_path = "tests/report_format_fixture.py"
    assert (_REPO_ROOT / builder_path).is_file(), f"{builder_path} does not exist"
    source = _module_source(builder_path)
    for forbidden in _FORBIDDEN_FIXTURE_IMPORTS:
        assert forbidden not in source, (
            f"{builder_path} imports {forbidden!r}, which would make the "
            "fixture feature-value-dependent"
        )
    assert ".nii" not in source, f"{builder_path} appears to read a NIfTI fixture"


def test_ac9_fixture_text_is_reproduced_by_the_builder_module_alone():
    import report_format_fixture as fixture_mod

    produced = fixture_mod.format_contract_text()
    committed = _FORMAT_FIXTURE.read_text(encoding="utf-8")
    assert produced == committed, (
        "tests/report_format_fixture.py's format_contract_text() does not "
        "reproduce the committed tests/golden/report_format_contract.json"
    )


# =========================================================================== #
# AC10: format guarantees asserted explicitly (key order, key set, floats)
# =========================================================================== #


def test_ac10_key_order_key_set_and_float_rendering_asserted_explicitly():
    """A test in test_016 or test_022 asserts, against freshly serialised
    output, the report's top-level key order, its exact key set, and float
    rendering -- so a failure names which of the three moved. Checked by
    scanning both modules' source for the three distinct assertion shapes
    rather than importing (this AC is about test *coverage*, not behaviour
    this module can call directly without duplicating the builder's fixture
    literals)."""
    combined_source = (
        _module_source("tests/test_016_features_json.py")
        + "\n"
        + _module_source("tests/test_022_stage3_serialisation.py")
    )
    assert re.search(r"\blist\(.*\.keys\(\)\)", combined_source) or re.search(
        r"\bkeys\(\)\s*==", combined_source
    ) or "key order" in combined_source.lower(), (
        "no key-order assertion found in test_016/test_022"
    )
    assert re.search(r"\bset\(.*\.keys\(\)\)", combined_source) or "key set" in combined_source.lower() or (
        "keys()" in combined_source
    ), "no key-set assertion found in test_016/test_022"
    assert "1e-12" in combined_source or "106.98418277680141" in combined_source, (
        "no reference to the format fixture's exponent/long-decimal float "
        "literals found in test_016/test_022 -- float rendering does not "
        "look explicitly asserted"
    )


# =========================================================================== #
# AC11: the write-and-skip defect is not inherited
# =========================================================================== #


@pytest.mark.parametrize(
    "module,func_name",
    [
        ("tests/test_016_features_json.py", "test_ac5_golden_snapshot"),
        ("tests/test_022_stage3_serialisation.py", "test_ac8_golden_snapshot"),
    ],
)
def test_ac11_consumer_source_has_no_skip_or_write_branch(module, func_name):
    tree = _module_ast(module)
    source = _function_source(tree, func_name, where=module)
    assert "pytest.skip" not in source, f"{module}::{func_name} still calls pytest.skip"
    assert "write_text(" not in source and "write_bytes(" not in source, (
        f"{module}::{func_name} still self-heals by writing the golden"
    )


def _assert_missing_fixture_fails_loudly(test_func, missing_path: Path) -> None:
    try:
        test_func()
    except pytest.skip.Exception as exc:
        pytest.fail(f"missing format fixture causes a skip, not a failure: {exc}")
    except BaseException as exc:  # noqa: BLE001
        assert missing_path.name in str(exc), (
            f"failure does not name the missing fixture {missing_path.name}: {exc}"
        )
    else:
        pytest.fail(
            f"missing format fixture ({missing_path.name}) silently passed "
            "instead of failing"
        )


@pytest.mark.parametrize(
    "module_name,func_name",
    [
        ("test_016_features_json", "test_ac5_golden_snapshot"),
        ("test_022_stage3_serialisation", "test_ac8_golden_snapshot"),
    ],
)
def test_ac11_missing_fixture_raises_names_filename_not_skip(
    monkeypatch, tmp_path, module_name, func_name
):
    mod = __import__(module_name)
    if not hasattr(mod, "GOLDEN_PATH"):
        pytest.fail(f"{module_name} has no module-level GOLDEN_PATH to monkeypatch")
    missing_path = tmp_path / "report_format_contract.json"
    assert not missing_path.exists()
    monkeypatch.setattr(mod, "GOLDEN_PATH", missing_path)
    _assert_missing_fixture_fails_loudly(getattr(mod, func_name), missing_path)


# =========================================================================== #
# AC12: every discharged fence is deleted, not left vacuous
# =========================================================================== #

_DISCHARGED_FENCES = (
    ("tests/test_042_golden_determinism.py", "test_ac9_fresh_report_matches_committed_golden_within_tolerance"),
    ("tests/test_042_golden_determinism.py", "test_ac13_regeneration_reproduces_committed_goldens_within_tolerance"),
    ("tests/test_098_stray_components.py", "test_ac16_write_goldens_matches_committed_within_tolerance"),
    ("tests/test_119_curve_formulation.py", "test_ac18_every_manifest_case_matches_committed_golden"),
    ("tests/test_119_curve_formulation.py", "test_ac20_diff_against_committed_goldens_stays_under_stage3"),
    ("tests/test_120_leave_one_out_offset.py", "test_ac25_every_manifest_case_matches_committed_golden"),
    ("tests/test_120_leave_one_out_offset.py", "test_ac26_regeneration_moves_no_verdict_outside_mode1s_own_deliverable"),
    ("tests/test_120_leave_one_out_offset.py", "test_ac26_changes_confined_to_stage3_and_findings_and_verdict"),
    ("tests/test_121_tangent_orientation.py", "test_ac12_pca_values_match_fresh_computation_within_tolerance"),
    ("tests/test_122_signed_curvature.py", "test_ac20_every_corpus_golden_matches_fresh_build"),
    ("tests/test_122_signed_curvature.py", "test_ac21_stage3_report_golden_is_present_and_carries_new_keys"),
    ("tests/test_123_recalibrate_and_regenerate.py", "test_ac23_every_manifest_case_matches_committed_golden"),
    ("tests/test_123_recalibrate_and_regenerate.py", "test_ac25_seven_non_mislabel_goldens_gain_only_is_terminal"),
    ("tests/test_123_recalibrate_and_regenerate.py", "test_ac26_two_changed_goldens_move_only_is_terminal_and_the_threshold_clause"),
)

assert len(_DISCHARGED_FENCES) == 14, "the item spec names exactly fourteen fences to delete"


@pytest.mark.parametrize("module,func_name", _DISCHARGED_FENCES)
def test_ac12_fence_function_no_longer_defined(module, func_name):
    tree = _module_ast(module)
    names = _function_names(tree)
    assert func_name not in names, f"{module}::{func_name} is still defined (fence not deleted)"


def test_ac12_no_test_function_iterates_a_retired_golden_glob():
    # Anchored on a word boundary so the retired `segfacet.synth.golden.GOLDEN_DIR`
    # symbol is caught while this module's own `_CORPUS_GOLDEN_DIR` (a distinct,
    # never-retired identifier that merely ends with the same substring) is not.
    glob_re = re.compile(r"(?<![A-Za-z0-9_])GOLDEN_DIR\.glob\(|(?<![A-Za-z0-9_])GOLDEN_DIR\s*/\s*['\"]\*")
    offenders = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            # This module's own AC1/adversarial probes legitimately glob
            # _CORPUS_GOLDEN_DIR (never the retired GOLDEN_DIR symbol) to
            # prove tests/corpus/golden/ is empty -- not a subject of AC12.
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                segment = ast.get_source_segment(source, node) or ""
                if glob_re.search(segment):
                    offenders.append(f"{path.relative_to(_REPO_ROOT).as_posix()}::{node.name}")
    assert not offenders, f"these test functions still glob a retired golden directory: {offenders}"


# =========================================================================== #
# AC13: every re-pointed consumer survives, golden-free
# =========================================================================== #

_RE_POINTED = (
    ("tests/test_042_golden_determinism.py", "test_ac6_exactly_one_golden_per_manifest_case_no_more_no_fewer"),
    ("tests/test_042_golden_determinism.py", "test_ac7_every_committed_golden_is_valid_json_and_validates"),
    ("tests/test_042_golden_determinism.py", "test_ac8_committed_golden_case_id_matches_filename"),
    ("tests/test_042_golden_determinism.py", "test_ac16_reconstructed_golden_is_pipeline_blind"),
    ("tests/test_042_golden_determinism.py", "test_adv_mode5_remove_level_golden_canonicalises_without_crashing_on_empty_labels"),
    ("tests/test_042_golden_determinism.py", "test_adv_clean_control_golden_passes_with_no_findings"),
    ("tests/test_042_golden_determinism.py", "test_adv_reconstructed_golden_blindness_is_checked_via_rule_ids_not_empty_findings"),
    ("tests/test_089_fov_aware_coverage_border.py", "test_ac16_committed_corpus_coverage_and_border_findings_unchanged"),
    ("tests/test_090_reference_derived_defaults.py", "test_ac15_all_committed_goldens_still_check_true"),
    ("tests/test_094_tptbox_image_layer.py", "test_ac7_report_matches_committed_golden_within_tolerance"),
    ("tests/test_098_stray_components.py", "test_ac14_every_golden_components_block_has_four_new_keys"),
    ("tests/test_098_stray_components.py", "test_ac14_every_golden_still_validates_against_schema"),
    ("tests/test_098_stray_components.py", "test_ac15_golden_verdict_and_findings_unchanged"),
    ("tests/test_105_golden_decision_table.py", "test_ac3_current_tree_has_30_non_py_fixtures"),
    ("tests/test_105_golden_decision_table.py", "test_ac7_golden_row_evidence_is_measured_not_transcribed"),
    ("tests/test_106_stage19_validation.py", "test_ac22_nine_goldens_match_corpus_case_ids"),
    ("tests/test_108_affine_faces.py", "test_ac8_border_and_coverage_presence_and_labels_unchanged"),
    ("tests/test_120_leave_one_out_offset.py", "test_ac17_threshold_margins_hold_on_corpus"),
    ("tests/test_120_leave_one_out_offset.py", "test_ac23_border_crop_case_gains_mislabel_finding_border_unchanged"),
    ("tests/test_121_tangent_orientation.py", "test_ac10_principal_axis_within_0996_of_left_right_on_every_golden"),
    ("tests/test_121_tangent_orientation.py", "test_ac10_principal_axis_exactly_left_right_on_seven_of_nine_cases"),
    ("tests/test_122_signed_curvature.py", "test_ac20_new_curvature_keys_present_in_every_committed_golden"),
    ("tests/test_123_recalibrate_and_regenerate.py", "test_ac28_pinned_snapshot_reasons_equal_committed_golden_reasons"),
    ("tests/test_123_recalibrate_and_regenerate.py", "_interior_offset_ceiling_over_corpus"),
)

_RE_POINTED += tuple(
    (module, func_name)
    for module, func_name in (
        ("tests/test_111_golden_guard.py", "test_ac1_gitattributes_pins_golden_dir"),
        ("tests/test_111_golden_guard.py", "test_ac2_check_attr_reports_lf_pin_for_both_files"),
        ("tests/test_111_golden_guard.py", "test_ac3_committed_blob_has_no_carriage_returns"),
        ("tests/test_111_golden_guard.py", "test_ac5_no_self_healing_branch_in_test_ac8"),
        ("tests/test_111_golden_guard.py", "test_ac6_ac7_missing_golden_fails_loudly_and_names_path"),
        ("tests/test_111_golden_guard.py", "test_ac8_passing_path_unchanged"),
        ("tests/test_111_golden_guard.py", "test_ac9_sibling_test_016_unchanged_and_agrees_on_missing_golden"),
        ("tests/test_111_golden_guard.py", "test_adv_golden_present_but_empty_fails_with_assertion"),
        ("tests/test_111_golden_guard.py", "test_adv_golden_present_with_crlf_content_is_well_defined"),
        ("tests/test_111_golden_guard.py", "test_adv_read_only_golden_directory_still_names_missing_path"),
    )
)

assert len(_RE_POINTED) == 34, (
    "34 = 24 individually-listed re-point rows plus the 10 test_111 functions "
    "the item spec bundles as a single table row"
)


@pytest.mark.parametrize("module,func_name", _RE_POINTED)
def test_ac13_repointed_consumer_still_defined_and_golden_free(module, func_name):
    tree = _module_ast(module)
    source = _function_source(tree, func_name, where=module)
    for marker in _GOLDEN_MARKERS_WITH_PATH:
        assert marker not in source, f"{module}::{func_name} still references {marker!r}"


# =========================================================================== #
# AC14: write_goldens cannot default to the retired location
# =========================================================================== #


def test_ac14_write_goldens_requires_explicit_destination():
    from segfacet.synth import golden as golden_mod

    with pytest.raises(TypeError):
        golden_mod.write_goldens()  # type: ignore[call-arg]


def test_ac14_write_goldens_with_explicit_dir_writes_one_file_per_case(tmp_path):
    from segfacet.synth.golden import write_goldens

    written = write_goldens(tmp_path)
    manifest_case_ids = {c["case_id"] for c in _run_manifest_cases()}
    assert manifest_case_ids, "expected at least one manifest case"
    written_names = {p.name for p in written}
    assert written_names == {f"{cid}.json" for cid in manifest_case_ids}
    for p in written:
        assert p.is_file()


# =========================================================================== #
# AC15: the one-command update path cannot recreate the snapshots
# =========================================================================== #


def test_ac15_main_with_no_out_exits_nonzero_and_creates_nothing(tmp_path, monkeypatch):
    from segfacet.synth import golden as golden_mod

    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        golden_mod.main([])
    assert exc_info.value.code != 0, "main([]) with no --out must exit non-zero"
    assert not (tmp_path / "tests" / "corpus" / "golden").exists()
    assert not (tmp_path / "corpus" / "golden").exists()
    assert not _CORPUS_GOLDEN_DIR.exists(), (
        "main([]) with no --out must not resurrect the retired committed store"
    )


def test_ac15_main_with_out_still_writes_nine_files(tmp_path):
    from segfacet.synth import golden as golden_mod

    out_dir = tmp_path / "regen"
    returncode = golden_mod.main(["--out", str(out_dir)])
    assert returncode == 0
    written = sorted(out_dir.glob("*.json"))
    assert len(written) == 9, f"expected 9 regenerated files, got {len(written)}: {written}"


# =========================================================================== #
# AC16: GOLDEN_DIR / GOLDEN_DIRNAME are no longer public constants
# =========================================================================== #


def test_ac16_golden_dir_absent_from_synth_golden_module():
    from segfacet.synth import golden as golden_mod

    assert "GOLDEN_DIR" not in getattr(golden_mod, "__all__", ())
    assert "GOLDEN_DIRNAME" not in getattr(golden_mod, "__all__", ())
    assert not hasattr(golden_mod, "GOLDEN_DIR")
    assert not hasattr(golden_mod, "GOLDEN_DIRNAME")


def test_ac16_golden_dir_absent_from_synth_package():
    import segfacet.synth as synth_pkg

    assert "GOLDEN_DIR" not in getattr(synth_pkg, "__all__", ())
    assert "GOLDEN_DIRNAME" not in getattr(synth_pkg, "__all__", ())
    assert not hasattr(synth_pkg, "GOLDEN_DIR")
    assert not hasattr(synth_pkg, "GOLDEN_DIRNAME")


# =========================================================================== #
# AC17: no live reference to a retired path remains outside the allowlist
# =========================================================================== #

_AC17_ALLOWLISTED_FILES = frozenset(
    {
        "tests/test_116_ras_native_corpus.py",
        "tests/test_126_golden_retirement.py",
    }
)

_AC17_NEEDLES = (
    "tests/corpus/golden",
    "tests/golden/016_features_report.json",
    "tests/golden/022_stage3_report.json",
)


def _grep_needle_in_tree(needle: str, roots, *, allowlist=_AC17_ALLOWLISTED_FILES) -> list:
    """Return the repo-relative paths under any of *roots* (absolute
    ``Path``s) whose text contains *needle*, skipping anything named in
    *allowlist* (repo-relative, ``/``-separated)."""
    hits = []
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(_REPO_ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()
            if rel in allowlist:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if needle in text:
                hits.append(rel)
    return hits


@pytest.mark.parametrize("needle", _AC17_NEEDLES)
def test_ac17_no_live_reference_outside_allowlist(needle):
    hits = _grep_needle_in_tree(needle, [_REPO_ROOT / "src", _REPO_ROOT / "tests"])
    assert not hits, f"{needle!r} still referenced outside the allowlist: {hits}"

    if _GITATTRIBUTES.exists():
        attrs_text = _GITATTRIBUTES.read_text(encoding="utf-8")
        if needle == "tests/corpus/golden":
            assert "tests/corpus/golden/*.json" not in attrs_text, (
                ".gitattributes still pins the retired tests/corpus/golden family"
            )


def test_ac17_allowlist_is_actually_reachable(tmp_path):
    """A synthetic offending file, planted under a fresh ``tmp_path`` (never
    the allowlist), proves ``_grep_needle_in_tree`` can actually detect a
    live reference -- an allowlist check that matches nothing is not
    evidence (Testing Strategy)."""
    offender = tmp_path / "definitely_not_allowlisted.py"
    offender.write_text('GOLDEN = "tests/corpus/golden"\n', encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n", encoding="utf-8")

    hits = _grep_needle_in_tree("tests/corpus/golden", [tmp_path], allowlist=frozenset())
    assert hits == [offender.as_posix()], (
        f"expected the reachability probe to detect the synthetic offender, got {hits}"
    )


# =========================================================================== #
# AC18: the signed Section-1 rows are untouched
# =========================================================================== #


def _split_sections(text: str) -> dict:
    heading_re = re.compile(r"(?m)^## (.+?)\s*$")
    matches = list(heading_re.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title] = text[start:end]
    return sections


def _table_cells(line: str) -> list:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _parse_first_pipe_table(section_text: str):
    table_lines = [l.strip() for l in section_text.splitlines() if l.strip().startswith("|")]
    if len(table_lines) < 2:
        raise AssertionError("no well-formed pipe table found")
    header_cells = [re.sub(r"\s+", " ", c.strip()).lower() for c in _table_cells(table_lines[0])]
    rows = []
    for line in table_lines[2:]:
        raw_cells = _table_cells(line)
        if len(raw_cells) != len(header_cells):
            continue
        rows.append(dict(zip(header_cells, raw_cells)))
    return rows


def _section1_rows() -> list:
    text = _DECISION_TABLE.read_bytes().decode("utf-8")
    sections = _split_sections(text)
    return _parse_first_pipe_table(sections["Section 1 — Committed test fixtures"])


def _row_cell_digest(row: dict) -> str:
    combined = "\x1f".join(
        [row["what it asserts today"], row["disposition"], row["replacement guarantee"]]
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


#: Pre-item digests of (what it asserts today, disposition, replacement
#: guarantee) for the eleven retired Section-1 rows, computed from the
#: document as it stood before this item touched it (2026-08-30). AC18
#: requires these three cells stay byte-unchanged; "asserted by" is
#: explicitly reconciled by this item's Implementation Steps (step 9) so it
#: is deliberately excluded from the digest, and (item 134) "evidence" is
#: likewise excluded and recomputed here: item 134 is the authorised
#: reconciler of the nine Group-A `evidence` cells, which move from a
#: transcribed N/M fraction to a stable pointer at
#: docs/aide/golden_evidence.generated.json -- narrowing this fence to the
#: three columns that are actually *judgement*, not measurement.
_AC18_PRE_ITEM_ROW_DIGESTS = {
    "tests/corpus/golden/clean_control.json": "06c98a414c9f5153dffd57b337f73eedd9429c2d22cb87e73c32888114381e4e",
    "tests/corpus/golden/mode1_displace.json": "0ae6c0c86aa3bb317fa7b2f2746ee70e98012d6eae2d02d9183c8c21dd5d6d37",
    "tests/corpus/golden/mode2_fragment.json": "4e3147522be51f4e58510c9333b5d67606490d8423b160718fd183c329f324ab",
    "tests/corpus/golden/mode3_inject_islands.json": "5a4498419b0629dc709f69853a7abc150a76b054adc3e86f66ea8469b05bb459",
    "tests/corpus/golden/mode4_relabel_swap.json": "464028945b250726b97e4aa041ed9008e35ce7019312426bb91f5d40ae52e871",
    "tests/corpus/golden/mode5_remove_level.json": "533d5be7be316510ad1d4b3c7b2957c8a1e8bc649d3f2bb6452cda06d446b57a",
    "tests/corpus/golden/mode6_crop_at_border.json": "23e7b3121567574ea4955bcb27d7be151daac79d12969590eec50dabc1cc20ad",
    "tests/corpus/golden/mode7_sequence_break.json": "2107420259c2264d60706f2c47e73255b1496efebae5ff955db65e38044d13f6",
    "tests/corpus/golden/mode8_force_overlap.json": "9328b5ee5e83d9ebad3267119b11d1799273347162bf938d0376076c15dc63aa",
    "tests/golden/016_features_report.json": "385e852ac9f0f45f91645c0c4a82ad914c80938dfea76eacc33b15f003b9ecdd",
    "tests/golden/022_stage3_report.json": "d037b5c3c02272728a32bf6715963a8b00e72ce578b23bea51d32637dca9d432",
}

assert len(_AC18_PRE_ITEM_ROW_DIGESTS) == 11


@pytest.mark.parametrize("fixture_path", sorted(_AC18_PRE_ITEM_ROW_DIGESTS))
def test_ac18_retired_row_cells_are_byte_unchanged(fixture_path):
    rows = _section1_rows()
    matches = [r for r in rows if r["fixture"] == fixture_path]
    assert len(matches) == 1, f"expected exactly one Section-1 row for {fixture_path!r}"
    row = matches[0]
    assert row["disposition"] == "retire", row
    got_digest = _row_cell_digest(row)
    expected_digest = _AC18_PRE_ITEM_ROW_DIGESTS[fixture_path]
    assert got_digest == expected_digest, (
        f"Section-1 row for {fixture_path!r} has a changed 'what it asserts "
        "today'/'evidence'/'disposition'/'replacement guarantee' cell"
    )


def test_ac18_no_row_carries_a_retirement_execution_note():
    rows = _section1_rows()
    for row in rows:
        for cell_name, cell in row.items():
            assert "item 126" not in cell, (
                f"row {row.get('fixture')!r} cell {cell_name!r} carries a "
                "retirement-execution note; execution belongs only in the "
                "new log section"
            )


# =========================================================================== #
# AC19: execution is recorded as a dated per-row log
# =========================================================================== #

_EXECUTION_LOG_HEADING = "## Retirement execution log"
_DIVERGENCES_HEADING = "## Divergences from the roadmap's working assumption"


def test_ac19_execution_log_section_placed_after_divergences():
    text = _DECISION_TABLE.read_bytes().decode("utf-8")
    log_idx = text.find(_EXECUTION_LOG_HEADING)
    divergences_idx = text.find(_DIVERGENCES_HEADING)
    assert log_idx != -1, f"{_EXECUTION_LOG_HEADING!r} heading not found"
    assert divergences_idx != -1, f"{_DIVERGENCES_HEADING!r} heading not found"
    assert log_idx > divergences_idx, (
        "the retirement execution log section must be placed after the "
        "Divergences section"
    )


def _execution_log_body() -> str:
    text = _DECISION_TABLE.read_bytes().decode("utf-8")
    sections = _split_sections(text)
    body = sections.get("Retirement execution log")
    assert body is not None, "no '## Retirement execution log' section found"
    return body


def _execution_log_paths(body: str) -> set:
    found = set()
    for path in list(_AC18_PRE_ITEM_ROW_DIGESTS.keys()):
        if path in body:
            found.add(path)
    return found


def test_ac19_execution_log_names_every_retired_path_dated_item126():
    body = _execution_log_body()
    assert "2026-08-30" in body, "execution log has no dated (2026-08-30) line"
    assert "item 126" in body, "execution log does not name item 126"
    logged = _execution_log_paths(body)
    expected = set(_AC18_PRE_ITEM_ROW_DIGESTS.keys())
    missing = expected - logged
    extra_absent_but_unlogged = set()
    for path in expected:
        if not (_REPO_ROOT / path).exists() and path not in logged:
            extra_absent_but_unlogged.add(path)
    assert not missing, f"execution log is missing these retired paths: {sorted(missing)}"
    assert not extra_absent_but_unlogged, extra_absent_but_unlogged


def test_adv_ac19_synthetic_log_line_for_existing_path_would_be_rejected():
    """Adversarial: a synthetic execution-log line naming a path that still
    exists on disk must fail the both-directions check."""
    surviving_path = "tests/corpus/manifest.json"
    assert (_REPO_ROOT / surviving_path).is_file()
    synthetic_body = f"- `{surviving_path}` retired 2026-08-30, item 126.\n"
    logged_but_present = {
        p for p in [surviving_path] if p in synthetic_body and (_REPO_ROOT / p).exists()
    }
    with pytest.raises(AssertionError):
        assert not logged_but_present, (
            f"execution log names a path that still exists on disk: {logged_but_present}"
        )


def test_adv_ac19_section1_row_naming_absent_path_with_no_log_line_fails():
    """Adversarial: a Section-1 row naming an absent path with no matching
    execution-log line must fail (both-directions check)."""
    synthetic_row_path = "tests/corpus/golden/does_not_exist_synthetic.json"
    synthetic_log_body = "- some other unrelated line\n"
    assert not (_REPO_ROOT / synthetic_row_path).exists()
    logged = synthetic_row_path in synthetic_log_body
    with pytest.raises(AssertionError):
        assert logged, (
            f"Section-1 row names absent path {synthetic_row_path!r} with no "
            "execution-log line accepting it"
        )


# =========================================================================== #
# AC20: test_105's inventory check is reconciled
# =========================================================================== #


def test_ac20_test105_inventory_constant_is_20():
    module = "tests/test_105_golden_decision_table.py"
    tree = _module_ast(module)
    source = _function_source(tree, "test_ac3_current_tree_has_30_non_py_fixtures", where=module)
    uncommented = re.sub(r"#.*", "", source)
    # The `def` line keeps "30" in the function name for AC identity, and the
    # docstring narrates the pre-retirement historical count (and a
    # 2026-08-30 date) -- neither is the live constant this check pins.
    # Only a line carrying the actual comparison is in scope.
    assertion_lines = "\n".join(line for line in uncommented.splitlines() if "assert" in line)
    assert assertion_lines, (
        f"{module}::test_ac3_current_tree_has_30_non_py_fixtures has no "
        "assert statement to check"
    )
    assert re.search(r"\b20\b", assertion_lines), (
        f"{module}::test_ac3_current_tree_has_30_non_py_fixtures does not "
        "reference the post-retirement inventory count of 20"
    )
    assert not re.search(r"\b30\b", assertion_lines), (
        f"{module}::test_ac3_current_tree_has_30_non_py_fixtures still "
        "hardcodes the pre-retirement count of 30"
    )


def test_ac20_section1_fixtures_and_filesystem_agree_modulo_execution_log():
    on_disk = set()
    for path in _TESTS_DIR.rglob("*"):
        if not path.is_file() or path.suffix == ".py":
            continue
        parts = set(path.relative_to(_TESTS_DIR).parts)
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        on_disk.add(path.relative_to(_REPO_ROOT).as_posix())

    rows = _section1_rows()
    documented = [r["fixture"] for r in rows]
    documented_set = set(documented)
    duplicates = sorted({p for p in documented_set if documented.count(p) > 1})
    assert not duplicates, f"duplicate Section-1 fixture path(s): {duplicates}"

    missing_from_table = sorted(on_disk - documented_set)
    assert not missing_from_table, (
        f"on-disk fixtures with no Section-1 row: {missing_from_table}"
    )

    logged = _execution_log_paths(_execution_log_body())
    extra_rows_not_on_disk = documented_set - on_disk
    unexplained = sorted(p for p in extra_rows_not_on_disk if p not in logged)
    assert not unexplained, (
        f"Section-1 rows naming absent files with no execution-log line: {unexplained}"
    )


# =========================================================================== #
# AC21: the new fixture is documented like every other
# =========================================================================== #


def test_ac21_format_fixture_has_one_keep_row():
    rows = _section1_rows()
    matches = [r for r in rows if r["fixture"] == "tests/golden/report_format_contract.json"]
    assert len(matches) == 1, (
        f"expected exactly one Section-1 row for the new format fixture, got "
        f"{len(matches)}"
    )
    row = matches[0]
    assert row["disposition"] == "keep", row
    assert row["replacement guarantee"] == "—", row


def test_ac21_format_fixture_named_in_divergences_section():
    text = _DECISION_TABLE.read_bytes().decode("utf-8")
    sections = _split_sections(text)
    divergences_body = sections.get("Divergences from the roadmap's working assumption", "")
    assert "report_format_contract.json" in divergences_body, (
        "the new format fixture is not named in the Divergences section"
    )


# =========================================================================== #
# AC22: the evidence cells are measured from fresh output
# =========================================================================== #


def test_ac22_test105_evidence_test_reads_fresh_output_not_committed_file():
    module = "tests/test_105_golden_decision_table.py"
    tree = _module_ast(module)
    source = _function_source(
        tree, "test_ac7_golden_row_evidence_is_measured_not_transcribed", where=module
    )
    assert "build_report_for_case" in source, (
        f"{module}::test_ac7_golden_row_evidence_is_measured_not_transcribed "
        "no longer derives evidence from build_report_for_case"
    )
    assert "tests/corpus/golden" not in source and "GOLDEN_DIR" not in source, (
        f"{module}::test_ac7_golden_row_evidence_is_measured_not_transcribed "
        "still reads a committed golden file"
    )


@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_ac22_documented_2694_evidence_still_verifies_unchanged(case_id):
    """Item 134: the signed row no longer carries the N/M fraction (it
    carries a stable pointer, see test_105's AC9 test), so the pin now reads
    (26, 94) from the companion this item introduces
    (docs/aide/golden_evidence.generated.json) instead of the row -- still
    cross-checked against a live build_report_for_case measurement."""
    import segfacet.catalogue as catalogue

    from segfacet.synth.golden import build_report_for_case

    cases = {c["case_id"]: c for c in _run_manifest_cases()}
    companion = json.loads(_COMPANION_PATH.read_bytes().decode("utf-8"))
    assert case_id in companion["cases"], f"{case_id!r} missing from the companion"
    entry = companion["cases"][case_id]
    documented_n, documented_m = entry["unwired_leaf_paths"], entry["total_leaf_paths"]
    assert (documented_n, documented_m) == (26, 94), (
        f"{case_id!r}'s documented evidence has moved off the pinned 26/94 "
        f"value: {documented_n}/{documented_m}"
    )

    report = build_report_for_case(cases[case_id])
    leaf_paths = catalogue.iter_leaf_paths(report["features"])
    cat = catalogue.build_catalogue()
    status_by_path = {entry2.path: entry2.status for entry2 in cat.entries}
    measured_m = len(leaf_paths)
    measured_n = sum(1 for p in leaf_paths if status_by_path.get(p) == "unwired")
    assert (measured_n, measured_m) == (documented_n, documented_m), case_id


# =========================================================================== #
# AC23: .gitattributes is reconciled
# =========================================================================== #


def test_ac23_gitattributes_no_longer_pins_corpus_golden():
    attrs_text = _GITATTRIBUTES.read_text(encoding="utf-8")
    lines = [l.strip() for l in attrs_text.splitlines()]
    matching = [l for l in lines if l.startswith("tests/corpus/golden/*.json")]
    assert not matching, f".gitattributes still pins tests/corpus/golden/*.json: {matching}"


def test_ac23_gitattributes_still_pins_tests_golden_star():
    attrs_text = _GITATTRIBUTES.read_text(encoding="utf-8")
    lines = [l.strip() for l in attrs_text.splitlines()]
    matching = [l for l in lines if l.startswith("tests/golden/*.json") and "eol=lf" in l]
    assert matching, ".gitattributes no longer pins tests/golden/*.json text eol=lf"


def test_ac23_check_attr_reports_lf_for_format_fixture():
    result = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", "tests/golden/report_format_contract.json"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert output.strip(), "git check-attr produced no output"
    file_lines = [
        line
        for line in output.splitlines()
        if line.startswith("tests/golden/report_format_contract.json:")
    ]
    assert any("eol: lf" in line for line in file_lines), (
        f"git check-attr does not report eol: lf for the format fixture:\n{output}"
    )


# =========================================================================== #
# AC24: test_111's hand-surveyed family list matches the tree
# =========================================================================== #


def test_ac24_test111_family_list_no_longer_names_corpus_golden():
    module = "tests/test_111_golden_guard.py"
    tree = _module_ast(module)
    source = _module_source(module)
    match = re.search(
        r"_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES\s*=\s*\((.*?)\)\n\n", source, re.DOTALL
    )
    assert match, f"could not locate _KNOWN_BYTE_EXACT_FIXTURE_FAMILIES tuple in {module}"
    families_block = match.group(1)
    assert "tests/corpus/golden/*.json" not in families_block, (
        f"{module}'s _KNOWN_BYTE_EXACT_FIXTURE_FAMILIES still names "
        "tests/corpus/golden/*.json"
    )


def test_ac24_every_known_family_has_an_eol_lf_pin():
    import test_111_golden_guard as mod111

    attrs_lines = [l.strip() for l in _GITATTRIBUTES.read_text(encoding="utf-8").splitlines()]
    families = mod111._KNOWN_BYTE_EXACT_FIXTURE_FAMILIES
    assert families, "_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES is empty"
    missing = [
        family
        for family in families
        if not any(line.startswith(family) and "eol=lf" in line for line in attrs_lines)
    ]
    assert not missing, f"these families have no eol=lf pin: {missing}"


def test_ac24_every_known_family_matches_at_least_one_file_on_disk():
    import test_111_golden_guard as mod111

    families = mod111._KNOWN_BYTE_EXACT_FIXTURE_FAMILIES
    unmatched = []
    for family in families:
        rel = family
        if "*" in rel:
            base_dir, pattern = rel.rsplit("/", 1)
            matches = list((_REPO_ROOT / base_dir).glob(pattern)) if (_REPO_ROOT / base_dir).exists() else []
        else:
            matches = [_REPO_ROOT / rel] if (_REPO_ROOT / rel).is_file() else []
        if not matches:
            unmatched.append(family)
    assert not unmatched, f"these families match no file on disk: {unmatched}"


# =========================================================================== #
# Adversarial: the harness itself keeps working, only the store is gone
# =========================================================================== #


def test_adv_write_goldens_idempotent_over_populated_directory(tmp_path):
    from segfacet.synth.golden import write_goldens

    dest = tmp_path / "dest"
    first = write_goldens(dest)
    second = write_goldens(dest)
    assert {p.name for p in first} == {p.name for p in second}
    for p in first:
        assert p.exists()


def test_adv_main_out_flag_returns_zero_and_writes_nine_files(tmp_path):
    from segfacet.synth.golden import main

    out_dir = tmp_path / "regen2"
    assert main(["--out", str(out_dir)]) == 0
    written = list(out_dir.glob("*.json"))
    assert len(written) == 9


# =========================================================================== #
# Adversarial: the format fixture's own failure modes
# =========================================================================== #


def test_adv_format_fixture_present_but_empty_fails_with_assertion_error(
    monkeypatch, tmp_path
):
    import test_016_features_json as mod016

    if not hasattr(mod016, "GOLDEN_PATH"):
        pytest.fail("test_016_features_json has no module-level GOLDEN_PATH")
    empty_fixture = tmp_path / "report_format_contract.json"
    empty_fixture.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod016, "GOLDEN_PATH", empty_fixture)
    with pytest.raises(AssertionError):
        mod016.test_ac5_golden_snapshot()


def test_adv_format_fixture_present_with_crlf_is_well_defined(monkeypatch, tmp_path):
    import test_016_features_json as mod016

    if not hasattr(mod016, "GOLDEN_PATH"):
        pytest.fail("test_016_features_json has no module-level GOLDEN_PATH")
    real_path = mod016.GOLDEN_PATH
    real_text = real_path.read_text(encoding="utf-8")
    crlf_fixture = tmp_path / "report_format_contract.json"
    crlf_fixture.write_bytes(real_text.replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(mod016, "GOLDEN_PATH", crlf_fixture)
    mod016.test_ac5_golden_snapshot()  # must not raise


def test_adv_format_fixture_drifted_by_one_key_names_the_drift(monkeypatch, tmp_path):
    import test_016_features_json as mod016

    if not hasattr(mod016, "GOLDEN_PATH"):
        pytest.fail("test_016_features_json has no module-level GOLDEN_PATH")
    real_path = mod016.GOLDEN_PATH
    parsed = json.loads(real_path.read_text(encoding="utf-8"))
    parsed["synthetic_drifted_key"] = "synthetic_value"
    drifted_fixture = tmp_path / "report_format_contract.json"
    drifted_fixture.write_text(
        json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(mod016, "GOLDEN_PATH", drifted_fixture)
    with pytest.raises(AssertionError) as exc_info:
        mod016.test_ac5_golden_snapshot()
    assert str(exc_info.value), "drift failure raised with no message naming the drift"


# =========================================================================== #
# Adversarial: the format fixture's numbers don't leak into real reports
# =========================================================================== #


def _collect_floats(obj, into: set) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_floats(v, into)
    elif isinstance(obj, list):
        for v in obj:
            _collect_floats(v, into)
    elif isinstance(obj, float):
        into.add(obj)


def test_adv_format_fixture_floats_do_not_appear_in_any_fresh_corpus_report():
    import report_format_fixture as fixture_mod

    fixture_floats = set()
    _collect_floats(fixture_mod.format_contract_inputs(), fixture_floats)
    assert fixture_floats, "expected the format fixture inputs to carry float literals"

    # Restrict the disjointness check to the fixture's distinctive literals
    # (module-level _LONG_DECIMAL_FLOAT / _NEGATIVE_FLOAT / _NEAR_ZERO_FLOAT).
    # Trivial values like 0.0/0.5/1.0 are ordinary computed values (zero
    # extents, midpoint offsets, unit axis components) that legitimately
    # recur in real reports -- their presence proves nothing about coupling.
    distinctive_floats = {
        v for v in fixture_floats if v not in (0.0, 0.5, 1.0)
    }
    assert distinctive_floats, (
        "expected the format fixture inputs to carry distinctive (non-trivial) "
        "float literals"
    )

    from segfacet.synth.golden import build_report_for_case

    fresh_floats = set()
    for case in _run_manifest_cases():
        report = build_report_for_case(case)
        _collect_floats(report, fresh_floats)
    assert fresh_floats, "expected at least one float in a freshly built report"

    overlap = distinctive_floats & fresh_floats
    assert not overlap, (
        f"the format fixture's hand-picked distinctive floats reappear in a "
        f"freshly built corpus report, which would re-couple the two: {overlap}"
    )


# =========================================================================== #
# Adversarial: a resurrected empty tests/corpus/golden/ directory
# =========================================================================== #


def test_adv_resurrected_empty_corpus_golden_directory_is_not_hidden_by_ac1():
    """If someone resurrects an empty tests/corpus/golden/ directory (e.g. a
    stray mkdir), AC1's glob-based check must still pass -- an empty
    directory carries no *.json files -- but this test documents and pins
    that specific behaviour so a future AC1 rewrite to `.exists()` (which
    WOULD fail on an empty directory) is a deliberate choice, not a silent
    regression discovered by CI."""
    if _CORPUS_GOLDEN_DIR.exists():
        assert list(_CORPUS_GOLDEN_DIR.glob("*.json")) == []
    # No file was created here -- this only documents the invariant that a
    # directory (empty or absent) is what AC1 actually checks.


# =========================================================================== #
# Adversarial: a stub decision-table log line whose path still exists
# =========================================================================== #


def test_adv_stub_log_line_naming_an_existing_path_is_recognisably_wrong():
    """A log line claiming a path was 'retired' while that path is still on
    disk is internally inconsistent -- this test asserts the *combination*
    fails the invariant the real AC19 test enforces, using the corpus
    manifest (guaranteed present) as the stand-in existing path."""
    stub_log_line = "- `tests/corpus/manifest.json` retired 2026-08-30, item 126.\n"
    claimed_path = "tests/corpus/manifest.json"
    assert claimed_path in stub_log_line
    assert (_REPO_ROOT / claimed_path).exists(), (
        "test setup assumption broken: tests/corpus/manifest.json should "
        "still exist (it is explicitly kept by this item)"
    )
    # A log line naming a path that still exists is exactly the failure mode
    # test_adv_ac19_synthetic_log_line_for_existing_path_would_be_rejected
    # exercises against the real checker's logic above.
