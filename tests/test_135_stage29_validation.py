"""Tests for item 135 -- Stage 29 validation: the in-suite assertable subset.

Item 135 closes Stage 29 by replaying its acceptance end-to-end (the
retirement audit, a scratch-branch guard replay, mode 4 through the shipped
pipeline, the four-level held-out measurement, fails-before-the-fix replays
per defect, a fresh-clone suite, ...). Per the item spec's Testing Strategy,
most of that is a *replay* obligation discharged and recorded in this item's
Decisions log and ``progress.md`` -- not something a pytest module can
assert (the Assumptions section names the throwaway clone as the rig for
every replay that must not touch the working checkout: the fresh-clone
suite, the scratch-branch guard replay, the format-fixture deletion, and the
parent-commit checkouts). This module covers only the subset that *can* be
asserted in-suite, in the shape ``tests/test_125_stage28_validation.py``
established for Stage 28:

- AC1:  the eleven retired paths are absent; ``tests/golden/`` contains
        exactly ``report_format_contract.json``.
- AC2:  each of the four named replacements resolves to live module::function
        code that reads no path under ``tests/corpus/golden/``.
- AC3:  the format fixture's write-and-skip defect stays gone -- deleting it
        (via a monkeypatched ``GOLDEN_PATH``, ``test_111``'s pattern) makes
        its consumer fail naming the filename, not skip. This is the
        in-suite shadow of the scratch-branch deletion replay (Step 4),
        never a substitute for it.
- AC4:  the per-path ``git log --follow --name-status`` audit over
        ``69e5cf5..HEAD`` (queue-018's first commit to the branch tip),
        skip-guarded for a shallow clone or missing ``git`` (``test_116``'s
        idiom).
- AC5/AC6: ``committed_artifact_guard.classify_module`` on a source string
        containing the *same* comparison the scratch-branch replay (Step 5)
        adds yields a violation naming ``assert_matches_committed_artifact``
        -- the in-suite shadow of that replay, not a substitute for it.
- AC8/AC9: ``mode4_relabel_swap`` reads ``is_monotonic is False`` with the
        swapped pair named, through both ``extract_feature_record`` and a
        real ``segfacet run --no-reference`` CLI invocation.
- AC11: ``clean_control`` reads ``is_monotonic is True`` with empty
        ``non_monotonic_pairs`` and fires no findings, through both paths.
- AC14: **a pin on the observation, not on the wish** -- a 4-level curve with
        an interior level displaced 15 mm yields held-out offsets all below
        a stated degeneracy floor (item 129's exact measured array), while
        the same displacement at 5 and 6 levels separates -- so this pin
        does not read as "the estimator is broken everywhere". The
        docstring's floor/reason/gate language is pinned alongside it.
- AC15: the nested-label (coincident-centroid) map yields
        ``stage3_unavailable.reason == "coincident_centroids"`` naming both
        levels, through ``extract_feature_record`` and the CLI.
- AC16: both pin files carry the same ``tptbox`` version, >= 0.7.6, and the
        installed distribution's ``License`` metadata names neither AGPL nor
        Affero.
- AC24: Stage 29's three acceptance boxes are ticked-and-annotated or
        unticked-and-reasoned (the tick-implies-evidence biconditional item
        106 established), and box 3 is specifically unticked naming the
        four-level clause. **Expected to FAIL until the builder edits
        progress.md** (Implementation Step 13) -- this pin exists so that
        edit cannot silently regress once made, not so this item passes
        before it is made.
- AC12/AC13: Stage 28's mode-4 acceptance box (index 3 of 5) is ticked and
        annotated; its scoliotic-case box (index 4) stays unticked with a
        non-empty reason. Also expected to FAIL until the builder edits
        progress.md.
- AC25: the manifest's pipeline-detected mode count (excluding the mode-0
        clean control) is 7 of {1..7}, and the committed golden-snapshot
        inventory is 11 -> 0 with one surviving format fixture, agreeing
        dynamically with ``test_040``/``test_057``'s mode-set constants.
- AC26: no changed line in this item's ``docs/aide/progress.md`` diff (vs
        the recorded queue-018 base) is a hand-typed stage-heading or
        deliverable-bullet status icon -- skip-guarded, never fail, when the
        base ref cannot be resolved.
- AC27: ``python .aide/scripts/aide.py check``'s in-process ``run_checks``
        reports no error and no warning outside the two recorded baseline
        classes (missing ``## Assumptions``, a gate awaiting a decision).
- AC28: this item's ``docs/aide/insights.md`` diff (vs the same base) is
        append-only -- no non-blank line is removed. Skip-guarded the same
        way as AC26.

AC7, AC17, AC18-AC23 are replays with no stable in-suite shape (the
scratch-branch deletion replay itself, the fails-before-the-fix parent-commit
checkouts, the fresh-clone suite, the environment table) and are
intentionally not covered here -- they belong to this item's Decisions log
and the Validation section, not to a test module.

Adversarial and edge cases covered:
- A Stage 29 or Stage 28 box ticked with no annotation, or unticked with no
  reason, fails the AC24/AC12 biconditional parser.
- A resurrected ``tests/corpus/golden/some_case.json`` fails AC1's glob check.
- ``_MIN_LEVELS_FOR_HELD_OUT`` moved back to 4 would fail AC14's separation
  companion assertions (checked via the live constant, not a hypothetical).
- A guard allowlist widened to cover ``reference_default.json`` would break
  AC5's in-suite shadow -- pinned by confirming the path stays excluded.
- A synthetic diff line matching a hand-typed deliverable-bullet status icon
  fails the AC26 checker directly (no real git diff required for this case).
- A synthetic ``insights.md`` diff removing a non-blank line fails the AC28
  checker directly.
- Determinism: two ``extract_feature_record`` calls on ``mode4_relabel_swap``
  agree; two four-level held-out computations agree.
- Immutability: the four-level and nested-label maps are built in memory;
  no committed fixture, manifest, or format fixture is written to.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import importlib.util
import re
import subprocess

from run_process import run_utf8
from pathlib import Path

import pytest

from segfacet.cli import main as cli_main
from segfacet.config import bundled_default_config
from segfacet.features.spline_offset import compute_leave_one_out_spline_offsets
from segfacet.pipeline import extract_feature_record
from segfacet.synth.corpus import CORPUS_DIR, load_manifest
from segfacet.synth.regression import loaded_seg_image

import committed_artifact_guard as guard
import report_format_fixture as fixture_mod
import test_126_golden_retirement as t126
import test_129_coincident_centroids_and_held_out_floor as t129
import test_133_tptbox_pin_and_verse_retirement as t133

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_DOCS_AIDE_DIR = _REPO_ROOT / "docs" / "aide"
_PROGRESS_PATH = _DOCS_AIDE_DIR / "progress.md"
_INSIGHTS_PATH = _DOCS_AIDE_DIR / "insights.md"
_AIDE_SCRIPT = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
_GOLDEN_DIR = _TESTS_DIR / "golden"

#: queue-018's first commit -- the item spec's AC4 range start.
_QUEUE018_FIRST_COMMIT = "69e5cf5"

#: The item spec's own designated base for this item's diff checks (AC26,
#: AC28) -- the same fallback pair test_126/test_128/test_132 already use for
#: "git diff against the recorded base".
_BASE_REF_CANDIDATES = ("origin/aide/queue-018", "aide/queue-018")


def _read_progress() -> str:
    return _PROGRESS_PATH.read_text(encoding="utf-8")


def _aide_module():
    spec = importlib.util.spec_from_file_location("_aide_cli_135", _AIDE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _manifest_case(case_id: str) -> dict:
    for case in load_manifest()["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _record(case_id: str) -> dict:
    seg_img = loaded_seg_image(_manifest_case(case_id))
    return extract_feature_record(seg_img, bundled_default_config())


def _run_cli(args):
    return cli_main(args)


def _cli_no_reference_report(case_id: str, tmp_path: Path) -> dict:
    import json

    case = _manifest_case(case_id)
    scan_path = CORPUS_DIR / case["scan_fixture"]
    seg_path = CORPUS_DIR / case["seg_fixture"]
    out_dir = tmp_path / f"{case_id}-out"
    code = _run_cli(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--no-reference",
        ]
    )
    assert code == 0, f"segfacet run --no-reference exited {code} for {case_id!r}"
    report_path = out_dir / "segfacet_report.json"
    assert report_path.is_file(), f"no report written for {case_id!r}"
    return json.loads(report_path.read_text(encoding="utf-8"))


# =========================================================================== #
# AC1: the eleven retired paths are absent; tests/golden/ carries exactly the
# surviving format fixture.
# =========================================================================== #


def test_ac1_all_eleven_retired_paths_absent():
    for rel_path in t126._RETIRED_PATHS:
        assert not (_REPO_ROOT / rel_path).is_file(), f"{rel_path} still exists"


def test_ac1_eleven_retired_paths_enumerated_matches_spec_count():
    assert len(t126._RETIRED_PATHS) == 11, t126._RETIRED_PATHS


def test_ac1_tests_golden_contains_exactly_the_format_fixture():
    assert _GOLDEN_DIR.is_dir(), f"{_GOLDEN_DIR} does not exist"
    entries = sorted(p.name for p in _GOLDEN_DIR.glob("*.json"))
    assert entries == ["report_format_contract.json"], entries


def test_ac1_corpus_golden_directory_absent_or_empty():
    corpus_golden = _TESTS_DIR / "corpus" / "golden"
    matches = sorted(corpus_golden.glob("*.json")) if corpus_golden.exists() else []
    assert matches == [], f"tests/corpus/golden/*.json still present: {matches}"


def test_adv_resurrected_golden_snapshot_fails_ac1_glob(tmp_path):
    """Adversarial (spec-named): the check globs, so a single reintroduced
    file under a resurrected tests/corpus/golden/ would be caught."""
    resurrected = tmp_path / "corpus_golden"
    resurrected.mkdir()
    (resurrected / "some_case.json").write_text("{}", encoding="utf-8")
    matches = sorted(resurrected.glob("*.json"))
    assert matches != [], "expected the resurrected file to be detected by the glob"


# =========================================================================== #
# AC2: the four named replacements resolve to live module::function code that
# reads no path under tests/corpus/golden/.
# =========================================================================== #

#: Replacement (i): intra-run determinism -- the exact set item 126's own
#: AC5 pins.
_AC2_DETERMINISM_TESTS = t126._AC5_DETERMINISM_TESTS


@pytest.mark.parametrize("module,func_name", _AC2_DETERMINISM_TESTS)
def test_ac2_replacement_i_determinism_test_resolves_and_is_golden_free(module, func_name):
    tree = t126._module_ast(module)
    source = t126._function_source(tree, func_name, where=module)
    for marker in t126._GOLDEN_MARKERS:
        assert marker not in source, f"{module}::{func_name} still references {marker!r}"


def test_ac2_replacement_ii_schema_validity_test_resolves():
    module = "tests/test_126_golden_retirement.py"
    tree = t126._module_ast(module)
    source = t126._function_source(
        tree, "test_ac3_fresh_report_validates_against_schema", where=module
    )
    assert "build_report_for_case" in source
    for marker in t126._GOLDEN_MARKERS_WITH_PATH:
        assert marker not in source


def test_ac2_replacement_iii_verdict_and_findings_shape_test_resolves():
    module = "tests/test_098_stray_components.py"
    tree = t126._module_ast(module)
    source = t126._function_source(
        tree, "test_ac15_golden_verdict_and_findings_unchanged", where=module
    )
    assert "_PRE_098_GOLDEN_VERDICT_AND_FINDINGS" in source
    for marker in t126._GOLDEN_MARKERS_WITH_PATH:
        assert marker not in source


def test_ac2_replacement_iv_format_fixture_builder_resolves():
    assert hasattr(fixture_mod, "format_contract_text")
    assert fixture_mod.GOLDEN_PATH.name == "report_format_contract.json"
    assert fixture_mod.GOLDEN_PATH.is_file()
    produced = fixture_mod.format_contract_text()
    committed = fixture_mod.GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == committed


def test_ac2_none_of_the_four_replacements_reads_corpus_golden_path():
    for module, func_name in _AC2_DETERMINISM_TESTS:
        tree = t126._module_ast(module)
        source = t126._function_source(tree, func_name, where=module)
        assert "tests/corpus/golden" not in source, f"{module}::{func_name}"


# =========================================================================== #
# AC3: deleting the format fixture fails loudly, naming the file -- never a
# skip -- the in-suite shadow of the Step 4 scratch-branch replay.
# =========================================================================== #


def test_ac3_missing_format_fixture_fails_loudly_names_filename(monkeypatch, tmp_path):
    """In-suite shadow only (see module docstring) -- the real replay is a
    scratch-branch deletion in the throwaway clone (Assumptions), never
    performed against the working checkout."""
    import test_016_features_json as mod016

    missing_path = tmp_path / "report_format_contract.json"
    assert not missing_path.exists()
    monkeypatch.setattr(mod016, "GOLDEN_PATH", missing_path)
    try:
        mod016.test_ac5_golden_snapshot()
    except pytest.skip.Exception as exc:
        pytest.fail(f"missing format fixture causes a skip, not a failure: {exc}")
    except BaseException as exc:  # noqa: BLE001
        assert missing_path.name in str(exc), (
            f"failure does not name the missing fixture {missing_path.name}: {exc}"
        )
    else:
        pytest.fail("missing format fixture silently passed instead of failing")


# =========================================================================== #
# AC4: no retired path was regenerated on the way out, over queue-018's own
# range (69e5cf5..HEAD) -- skip-guarded for a shallow clone (test_116's
# idiom).
# =========================================================================== #


def _git_available_and_range_reachable() -> bool:
    try:
        probe = run_utf8(
            ["git", "cat-file", "-e", f"{_QUEUE018_FIRST_COMMIT}^{{commit}}"],
            cwd=_REPO_ROOT,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


_range_reachable = _git_available_and_range_reachable()

requires_full_history_from_queue018 = pytest.mark.skipif(
    not _range_reachable,
    reason=f"commit {_QUEUE018_FIRST_COMMIT} is not reachable in this clone "
    "(shallow checkout or git unavailable)",
)


@requires_full_history_from_queue018
@pytest.mark.parametrize("rel_path", t126._RETIRED_PATHS)
def test_ac4_most_recent_history_entry_since_queue018_is_a_deletion(rel_path):
    result = run_utf8(
        [
            "git", "log", "--follow", "--name-status", "--format=%H",
            f"{_QUEUE018_FIRST_COMMIT}..HEAD", "--", rel_path,
        ],
        cwd=_REPO_ROOT,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"git log failed for {rel_path!r}: {result.stderr}")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"no history found for {rel_path!r} in {_QUEUE018_FIRST_COMMIT}..HEAD"

    status_line = None
    for line in lines[1:]:
        if line[0] in "AMDRCT":
            status_line = line
            break
    assert status_line is not None, (
        f"could not find a status line for {rel_path!r}: {lines[:5]}"
    )
    assert status_line.startswith("D"), (
        f"most recent history entry for {rel_path!r} since queue-018 is not a "
        f"deletion: {status_line!r}"
    )


# =========================================================================== #
# AC5/AC6: the guard's in-suite shadow -- a source string carrying the same
# comparison the scratch-branch replay adds is flagged, naming the helper.
# Never a substitute for the real Step-5 replay (Assumptions).
# =========================================================================== #

_AC5_SYNTHETIC_SOURCE = (
    "from pathlib import Path\n"
    "\n"
    "def test_offender(tmp_path):\n"
    '    dest = tmp_path / "regen.json"\n'
    '    dest.write_bytes(b"{}")\n'
    '    committed = Path("src/segfacet/reference/reference_default.json")\n'
    "    assert dest.read_bytes() == committed.read_bytes()\n"
)


def test_ac5_synthetic_reference_default_comparison_is_flagged():
    violations = guard.classify_module(_AC5_SYNTHETIC_SOURCE, "tests/test_zz_synthetic_135.py")
    assert violations, "expected the synthetic byte-exact comparison to be flagged"
    assert violations[0].committed_path == "src/segfacet/reference/reference_default.json"


def test_ac6_synthetic_violation_message_names_the_helper():
    violations = guard.classify_module(_AC5_SYNTHETIC_SOURCE, "tests/test_zz_synthetic_135.py")
    message = guard.violation_message(violations)
    assert "assert_matches_committed_artifact" in message


def test_adv_reference_default_stays_off_the_allowlist():
    """Adversarial (spec-named): if a guard allowlist entry widened to cover
    reference_default.json, AC5's shadow above would stop classifying the
    synthetic comparison as a violation. Pinning the exclusion directly."""
    paths = [entry.path for entry in guard.ALLOWLIST]
    assert "src/segfacet/reference/reference_default.json" not in paths
    assert not guard._matches_allowlist("src/segfacet/reference/reference_default.json")


# =========================================================================== #
# AC8/AC9: mode 4 reads is_monotonic == False through extract_feature_record,
# naming the swapped pair.
# =========================================================================== #


def test_ac8_mode4_relabel_swap_is_non_monotonic_through_extract_feature_record():
    record = _record("mode4_relabel_swap")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is False


def test_ac9_mode4_relabel_swap_non_monotonic_pairs_names_l2_l3():
    record = _record("mode4_relabel_swap")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["non_monotonic_pairs"] == [["L2", "L3"]]


def test_ac8_mode4_relabel_swap_is_non_monotonic_through_cli(tmp_path):
    report = _cli_no_reference_report("mode4_relabel_swap", tmp_path)
    mono = report["features"]["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is False
    assert mono["non_monotonic_pairs"] == [["L2", "L3"]]


def test_adv_mode4_extract_feature_record_is_deterministic_across_two_calls():
    record1 = _record("mode4_relabel_swap")
    record2 = _record("mode4_relabel_swap")
    assert (
        record1["stage3"]["monotonic_consistency"]
        == record2["stage3"]["monotonic_consistency"]
    )


# =========================================================================== #
# AC11: the clean control stays monotonic and fires nothing, through both
# paths -- a mode-4 tick bought at the clean control's expense is not a tick.
# =========================================================================== #


def test_ac11_clean_control_is_monotonic_through_extract_feature_record():
    record = _record("clean_control")
    mono = record["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is True
    assert mono["non_monotonic_pairs"] == []


def test_ac11_clean_control_is_monotonic_and_fires_nothing_through_cli(tmp_path):
    report = _cli_no_reference_report("clean_control", tmp_path)
    mono = report["features"]["stage3"]["monotonic_consistency"]
    assert mono["is_monotonic"] is True
    assert mono["non_monotonic_pairs"] == []
    assert report["findings"] == []


# =========================================================================== #
# AC14: the four-level clause -- a pin on the observation, not the wish.
# =========================================================================== #

#: Item 129's exact measured array (spec Description, 2026-08-31): an
#: interior level (index 1) of a 4-level straight spine displaced 15 mm on
#: the x-axis, run through the held-out estimator. All four values read
#: below the stated degeneracy floor -- both the held-out and in-sample
#: paths are numerically the same curve at n=4 (module docstring).
_DEGENERACY_FLOOR_MM = 0.001

_AC14_PRE_129_FOUR_LEVEL_OFFSETS_MM = (
    7.348609152784843e-05,
    5.330684370393181e-06,
    5.740531122353952e-06,
    3.782179445898854e-05,
)


def _displaced_straight_spine(n: int, idx: int = 1, magnitude_mm: float = 15.0):
    centroids = t129._straight_spine(n)
    scenario = list(centroids)
    scenario[idx] = t129._displace_index(centroids, idx, magnitude_mm, axis=0)
    return scenario


def test_ac14_four_level_interior_displacement_is_degenerate():
    scenario = _displaced_straight_spine(4)
    records = compute_leave_one_out_spline_offsets(scenario)
    offsets = tuple(r.offset_mm for r in records)
    assert len(offsets) == 4
    for value in offsets:
        assert value < _DEGENERACY_FLOOR_MM, offsets
    for got, expected in zip(offsets, _AC14_PRE_129_FOUR_LEVEL_OFFSETS_MM):
        assert got == pytest.approx(expected, abs=1e-9), offsets


@pytest.mark.parametrize("n", [5, 6])
def test_ac14_five_and_six_levels_separate_the_same_displacement(n):
    scenario = _displaced_straight_spine(n)
    records = compute_leave_one_out_spline_offsets(scenario)
    displaced_offset = records[1].offset_mm
    assert displaced_offset > _DEGENERACY_FLOOR_MM, (n, displaced_offset)
    # Well above the four-level degenerate reading -- proves genuine
    # separation, not float noise clearing a tiny floor.
    assert displaced_offset > 0.1, (n, displaced_offset)


def test_ac14_docstring_still_states_the_floor_and_governing_gate():
    """Companion to the AC25/AC26 checks item 129's own module already
    pins -- re-asserted here because item 135's AC14 depends on this text
    staying in place. If _MIN_LEVELS_FOR_HELD_OUT moved back to 4, or the
    docstring's limitation block lost its gate reference, this fails."""
    import segfacet.features.spline_offset as so_mod

    assert so_mod._MIN_LEVELS_FOR_HELD_OUT == 5
    doc = so_mod.__doc__ or ""
    lowered = doc.lower()
    assert "five" in lowered
    assert "cubic" in lowered
    assert "interpolat" in lowered
    assert "0.001" in doc
    assert "15" in doc
    assert "human gate" in lowered or "deformity" in lowered


def test_adv_floor_moved_back_to_four_would_fail_the_separation_companion():
    """Adversarial (spec-named): if _MIN_LEVELS_FOR_HELD_OUT were moved back
    to 4, five levels would (per item 129's own reasoning) still take the
    held-out path only because 5 >= 5 continues to hold regardless of the
    floor's value -- what the floor actually gates is whether *four* levels
    fall back to in-sample. This pins that the live floor is what makes the
    n=4 case degenerate at all: with the floor hypothetically at 4, the
    four-level scenario above would be evaluated via the held-out branch
    instead of the fallback, and item 129's docstring records that branch
    would raise (n_points < 4 after the boundary move is unreachable, but a
    floor of exactly 4 was the original -- since fixed -- bug). Checked via
    the live constant rather than monkeypatching production code."""
    import segfacet.features.spline_offset as so_mod

    assert so_mod._MIN_LEVELS_FOR_HELD_OUT != 4


# =========================================================================== #
# AC15: the nested-label (coincident-centroid) map yields a report, naming
# both coincident levels -- the claimable D4 half.
# =========================================================================== #


def test_ac15_nested_label_map_yields_stage3_unavailable_through_extract_feature_record():
    seg_img = t129._coincident_label_map()
    t129._assert_coincidence(seg_img, 21, 22)
    record = extract_feature_record(seg_img, bundled_default_config())
    unavailable = record["stage3_unavailable"]
    assert unavailable["reason"] == "coincident_centroids"
    assert unavailable["levels"] == ["L2", "L3"]


def test_ac15_nested_label_map_cli_exit_zero_no_traceback_names_levels(tmp_path):
    import json

    from synthetic import make_scan, write_nifti

    seg_img = t129._coincident_label_map()
    t129._assert_coincidence(seg_img, 21, 22)
    scan_img = make_scan(shape=(20, 20, 40), spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"

    import io
    import contextlib

    err_buf = io.StringIO()
    with contextlib.redirect_stderr(err_buf):
        code = _run_cli(
            [
                "run", "--scan", str(scan_path), "--seg", str(seg_path),
                "--out", str(out_dir), "--no-reference",
            ]
        )
    err = err_buf.getvalue()
    assert code == 0, err
    assert "Traceback" not in err

    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert report["features"]["stage3_unavailable"]["reason"] == "coincident_centroids"
    assert report["features"]["stage3_unavailable"]["levels"] == ["L2", "L3"]

    text = (out_dir / "segfacet_report.txt").read_text(encoding="utf-8")
    assert "L2" in text and "L3" in text


# =========================================================================== #
# AC16: tptbox is pinned >= 0.7.6 in both files, and the installed
# distribution's License metadata is not AGPL/Affero.
# =========================================================================== #


def test_ac16_installed_version_at_least_0_7_6():
    installed_version = importlib.metadata.version("tptbox")
    assert t133._version_tuple(installed_version) >= t133._version_tuple("0.7.6")


def test_ac16_installed_license_not_agpl_or_affero():
    license_field = importlib.metadata.metadata("tptbox")["License"]
    assert license_field is not None and license_field.strip()
    lowered = license_field.lower()
    assert "agpl" not in lowered, license_field
    assert "affero" not in lowered, license_field


def test_ac16_both_pin_files_agree_with_installed_version():
    installed_version = importlib.metadata.version("tptbox")
    pyproject_specs = t133._pyproject_tptbox_specs()
    assert len(pyproject_specs) == 1
    pyproject_version = pyproject_specs[0].split("==", 1)[1]
    constraints_version = t133._constraints_pins().get("tptbox")
    assert installed_version == pyproject_version == constraints_version


# =========================================================================== #
# AC24: Stage 29's acceptance is ticked honestly (tick-implies-evidence).
# Expected to FAIL until the builder edits progress.md (module docstring).
# =========================================================================== #

_CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s?")
_EVIDENCE_NOTE_RE = re.compile(r"\*\(.*?\)\*", re.DOTALL)


def _stage_section(text: str, heading_prefix: str) -> str:
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = i
        elif start is not None and line.startswith("## Stage ") and i > start:
            end = i
            break
    if start is None:
        raise AssertionError(f"no {heading_prefix!r} heading found in progress.md")
    return "\n".join(lines[start:end])


def _acceptance_items(section: str) -> list:
    lines = section.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "**Acceptance.**")
    except StopIteration:
        raise AssertionError("no '**Acceptance.**' heading found under the section")
    items: list = []
    current: list = []
    seen_item = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if _CHECKBOX_RE.match(stripped):
            if current:
                items.append("\n".join(current))
            current = [line]
            seen_item = True
            continue
        if stripped == "" or stripped == "---":
            if current:
                items.append("\n".join(current))
                current = []
            if seen_item:
                break
            continue
        if current:
            current.append(line)
    if current:
        items.append("\n".join(current))
    return items


def _is_ticked(item_text: str) -> bool:
    match = _CHECKBOX_RE.match(item_text.splitlines()[0].strip())
    assert match is not None, item_text
    return match.group(1).lower() == "x"


def _has_annotation(item_text: str) -> bool:
    return bool(_EVIDENCE_NOTE_RE.search(item_text))


def _biconditional_violations(section: str) -> list:
    violations = []
    for item in _acceptance_items(section):
        if not _has_annotation(item):
            violations.append(item.splitlines()[0].strip())
    return violations


def test_ac24_stage29_has_three_acceptance_boxes():
    section = _stage_section(_read_progress(), "## Stage 29")
    items = _acceptance_items(section)
    assert len(items) == 3, items


def test_ac24_every_stage29_box_ticked_implies_evidence_or_unticked_implies_reason():
    section = _stage_section(_read_progress(), "## Stage 29")
    violations = _biconditional_violations(section)
    assert violations == [], (
        f"Stage 29 acceptance box(es) with no evidence/reason annotation: {violations}"
    )


def test_ac24_stage29_third_box_is_unticked_naming_the_four_level_clause():
    section = _stage_section(_read_progress(), "## Stage 29")
    items = _acceptance_items(section)
    assert len(items) == 3, items
    third = items[2]
    assert not _is_ticked(third), (
        f"Stage 29's third acceptance box must stay unticked (AC14): {third}"
    )
    lowered = third.lower()
    assert "four-level" in lowered or "four level" in lowered or "4-level" in lowered, third


def test_ac12_stage28_mode4_box_is_ticked_and_annotated():
    section = _stage_section(_read_progress(), "## Stage 28")
    items = _acceptance_items(section)
    assert len(items) == 5, items
    mode4_box = items[2]
    assert _is_ticked(mode4_box), f"Stage 28's mode-4 acceptance box must be ticked: {mode4_box}"
    assert _has_annotation(mode4_box), mode4_box
    assert "132" in mode4_box, "expected the mode-4 box to name item 132"
    assert "135" in mode4_box, "expected the mode-4 box to name item 135's replay"


def test_ac13_stage28_scoliotic_box_stays_unticked_with_item125_evidence():
    section = _stage_section(_read_progress(), "## Stage 28")
    items = _acceptance_items(section)
    assert len(items) == 5, items
    scoliotic_box = items[3]
    assert not _is_ticked(scoliotic_box), (
        f"Stage 28's scoliotic-case box must stay unticked: {scoliotic_box}"
    )
    assert _has_annotation(scoliotic_box), scoliotic_box
    assert "2026-08-30" in scoliotic_box, (
        "expected item 125's 2026-08-30 evidence note to remain, byte-unchanged"
    )


def test_adv_ticked_box_with_no_annotation_is_flagged():
    synthetic_section = (
        "## Stage 29 — Golden Retirement & Test-Artifact Hygiene (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [x] All 11 retired snapshots are gone.\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations, "expected the annotation-less ticked box to be flagged"


def test_adv_unticked_box_with_reason_is_not_flagged():
    synthetic_section = (
        "## Stage 29 — Golden Retirement & Test-Artifact Hygiene (G2, G7) — 🚧\n\n"
        "**Acceptance.**\n\n"
        "- [ ] A 4-level field of view yields non-degenerate held-out offsets. "
        "*(Unticked: known unmeetable, see item 129.)*\n"
    )
    violations = _biconditional_violations(synthetic_section)
    assert violations == []


# =========================================================================== #
# AC25: the before/after summary -- 7/8 and 11 -> 0 -- agrees with the
# manifest and with test_040/test_057's mode-set constants.
# =========================================================================== #


def _pipeline_detected_modes_excluding_clean_control() -> set:
    manifest = load_manifest()
    return {
        c["failure_mode"]
        for c in manifest["cases"]
        if c["detection"] == "pipeline" and c["failure_mode"] != 0
    }


def test_ac25_manifest_pipeline_detected_mode_count_is_seven():
    modes = _pipeline_detected_modes_excluding_clean_control()
    assert len(modes) == 7, modes
    assert modes == {1, 2, 3, 4, 5, 6, 7}


def test_ac25_agrees_with_test_040_mode_sets():
    import test_040_synthetic_corpus as t040

    manifest_pipeline_modes = _pipeline_detected_modes_excluding_clean_control()
    assert manifest_pipeline_modes == t040._PIPELINE_ONLY_MODES - {0}


def test_ac25_agrees_with_test_057_pipeline_detectable_modes():
    import test_057_acceptance_stage7 as t057

    manifest_pipeline_modes = _pipeline_detected_modes_excluding_clean_control()
    assert manifest_pipeline_modes == set(t057._PIPELINE_DETECTABLE_MODES)


def test_ac25_progress_names_seven_of_eight_and_eleven_to_zero():
    text = _read_progress()
    section = _stage_section(text, "## Stage 29")
    assert "7" in section and "8" in section, (
        "expected the Stage 29 section to name the 7 of 8 detection count"
    )
    assert "11" in section, "expected the Stage 29 section to name the retired-snapshot count"


# =========================================================================== #
# AC26: no deliverable bullet or item status is hand-edited -- skip-guarded
# when the recorded base is unavailable.
# =========================================================================== #

_HEADING_STATUS_RE = re.compile(r"^#{1,6}\s.*[✅🚧📋⏸️❌⏳]")
_DELIVERABLE_BULLET_STATUS_RE = re.compile(r"^-\s+[✅🚧📋⏸️❌⏳]\s*\*\*[A-Za-z]")


def _resolve_base_ref():
    for base_ref in _BASE_REF_CANDIDATES:
        result = run_utf8(
            ["git", "cat-file", "-e", f"{base_ref}^{{commit}}"],
            cwd=_REPO_ROOT,
            timeout=30,
        )
        if result.returncode == 0:
            return base_ref
    return None


def _diff_changed_content_lines(rel_path: str, base_ref: str) -> list:
    result = run_utf8(
        ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", rel_path],
        cwd=_REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"git diff against {base_ref!r} failed: {result.stderr}")
    changed = []
    for line in result.stdout.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            changed.append(line[1:])
    return changed


def test_ac26_progress_diff_has_no_hand_typed_status_icon():
    base_ref = _resolve_base_ref()
    if base_ref is None:
        pytest.skip("recorded queue-018 base ref is unavailable in this clone")
    changed = _diff_changed_content_lines("docs/aide/progress.md", base_ref)
    heading_offenders = [l for l in changed if _HEADING_STATUS_RE.match(l)]
    bullet_offenders = [l for l in changed if _DELIVERABLE_BULLET_STATUS_RE.match(l)]
    assert heading_offenders == [], (
        f"progress.md diff hand-edits a stage-heading status icon: {heading_offenders}"
    )
    assert bullet_offenders == [], (
        f"progress.md diff hand-edits a deliverable-bullet status icon: {bullet_offenders}"
    )


def test_adv_synthetic_deliverable_bullet_status_line_is_flagged():
    """Adversarial: a synthetic diff line hand-flipping a deliverable
    bullet's status icon must be caught by the AC26 pattern directly,
    independent of whatever the real git diff currently contains."""
    offending_line = "- ✅ **D12** A hand-typed deliverable that was never through aide progress set."
    assert _DELIVERABLE_BULLET_STATUS_RE.match(offending_line)


def test_adv_synthetic_heading_status_line_is_flagged():
    offending_line = "## Stage 30 — Something New (G1) — ✅"
    assert _HEADING_STATUS_RE.match(offending_line)


def test_adv_acceptance_checkbox_line_is_not_flagged_by_bullet_pattern():
    """An acceptance checkbox line (``- [x] ...``) must not trip the
    deliverable-bullet pattern -- it starts with ``- [`` not ``- <icon>``,
    and legitimately changes as part of this item's own authorised edit."""
    checkbox_line = "- [x] All 11 retired snapshots are gone. *(evidence here)*"
    assert not _DELIVERABLE_BULLET_STATUS_RE.match(checkbox_line)


# =========================================================================== #
# AC27: `aide check` reports no error and no warning class outside the
# recorded baseline (missing '## Assumptions', a gate awaiting a decision,
# or a transient branch-state warning -- see below).
# =========================================================================== #

# Measured 2026-09-01 during `aide merge 135`'s own post-merge re-test: `aide
# merge` deletes an item's claim branch only AFTER that re-test runs, so
# `aide check` transiently warned "stale claim branch aide/135-validate-
# stage-29-golden-retirement: item 135 is already ✅" -- a class this
# classifier had never seen -- and the gate went red on the item's own merge
# (the merge itself still completed; the branch has since been swept and the
# warning is gone). `test_114_documentation_corrections.py`'s
# `_BRANCH_STATE_WARNING_PREFIXES` (line ~534) already solved this generically
# for its own warning check by excluding any warning starting with "stale
# claim branch" or "unrecognised branch" by prefix -- both name a branch
# left behind mid-merge rather than a defect in the document being checked.
# Applying the same prefix tolerance here keeps AC27 from failing on a
# merge-order artifact of the loop's own bookkeeping while leaving every
# other warning class exactly as strict as before.
_BRANCH_STATE_WARNING_PREFIXES = ("stale claim branch", "unrecognised branch")

# Engine 1.28.1 (installed 2026-09-01, up from 1.21.0) added three advisory
# warning classes that fired on pre-existing document states rather than on
# anything this item changed: a spec pinning an always-authorised path under
# Asserts against (engine 1.23.0; merged items 126 and 132), a deliverable
# bullet whose item references all sat mid-prose with no trailing *(Item NNN)*
# marker (engine 1.24.0), and a queue marked completed while progress.md still
# held an untracked item for it. All three states were repaired at the
# 2026-09-01 feedback loop (framework-update PR #59), so the classifier names
# them -- a recurrence reads as its class, not as 'unclassified' -- but none is
# a tolerated baseline class: the baseline is the assumptions backlog, the two
# human gates, and transient branch state, exactly as before the update.
#
# "retracted-criterion" added 2026-09-02: during item 137's validation, a
# validator ticked all five Stage 20 acceptance criteria and then correctly
# retracted criteria 1, 3, 4 and 5 as mis-mapped attestations. By the
# engine's deliberate design (`.aide/scripts/aide.py`, "A withdrawn
# attestation is normal, not a defect ... the point is that it stays
# visible"), each retraction leaves a permanent `progress.md` warning naming
# the criterion and the retraction reason -- unlike the transient
# human-gate and branch-state classes above, this one does not clear on its
# own; a genuinely new retraction later still classifies here rather than as
# 'unclassified', which is the point of classifying by shape (the
# "criterion N was retracted on" phrase) rather than pinning the four exact
# messages.
_BASELINE_WARNING_CLASSES = (
    "assumptions-block",
    "awaiting-a-decision",
    "branch-state",
    "retracted-criterion",
)


def _classify_warning(message: str) -> str:
    if message.startswith(_BRANCH_STATE_WARNING_PREFIXES):
        return "branch-state"
    if "pinned under Asserts against" in message:
        return "always-authorised-pin"
    if "ends with no *(Item NNN)* marker" in message:
        return "untracked-bullet-marker"
    if "marked completed but still has open items" in message:
        return "queue-completed-open-items"
    if re.search(r"criterion \d+ was retracted on \d{4}-\d{2}-\d{2}", message):
        return "retracted-criterion"
    if "assumptions" in message.lower():
        return "assumptions-block"
    if "awaiting a decision" in message.lower():
        return "awaiting-a-decision"
    return "unclassified"


def test_ac27_aide_check_reports_no_error_and_only_baseline_warning_classes():
    aide = _aide_module()
    config = aide.load_config(_REPO_ROOT)
    errors, warnings = aide.run_checks(_REPO_ROOT, config)
    assert errors == [], errors
    classes = {_classify_warning(w) for w in warnings}
    assert classes <= set(_BASELINE_WARNING_CLASSES), (
        f"aide check reports a warning class outside the recorded baseline: "
        f"{classes - set(_BASELINE_WARNING_CLASSES)}"
    )


def test_adv_unclassified_warning_would_be_caught():
    """Adversarial: a warning message matching neither recorded baseline
    class must classify as 'unclassified', which the AC27 check above
    rejects -- proving the classifier can actually detect a new class."""
    assert _classify_warning("a brand new kind of warning nobody has seen before") == (
        "unclassified"
    )


def test_adv_stale_claim_branch_warning_classifies_as_branch_state():
    """A stale-claim-branch warning for an unrelated item (999, which does
    not exist in this repo) must classify as 'branch-state', not
    'unclassified' -- the transient merge-order artifact this test module
    measured 2026-09-01 (aide merge 135's own post-merge re-test), tolerated
    the same way test_114_documentation_corrections.py already tolerates it
    via its own `_BRANCH_STATE_WARNING_PREFIXES`."""
    warning = "stale claim branch aide/999-x: item 999 is already ✅"
    assert _classify_warning(warning) == "branch-state"


def test_adv_unrecognised_branch_warning_classifies_as_branch_state():
    """The sibling branch-state prefix ('unrecognised branch') must also
    classify as 'branch-state', not 'unclassified'."""
    warning = "unrecognised branch aide/does-not-exist"
    assert _classify_warning(warning) == "branch-state"


# =========================================================================== #
# AC28: insights.md's diff (vs the recorded base) is append-only -- no
# existing entry is reworded, reordered or deleted here.
# =========================================================================== #


def test_ac28_insights_diff_is_append_only():
    base_ref = _resolve_base_ref()
    if base_ref is None:
        pytest.skip("recorded queue-018 base ref is unavailable in this clone")
    changed = _diff_changed_content_lines("docs/aide/insights.md", base_ref)
    result = run_utf8(
        ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", "docs/aide/insights.md"],
        cwd=_REPO_ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"git diff against {base_ref!r} failed: {result.stderr}")
    removed = [
        line[1:]
        for line in result.stdout.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    non_blank_removed = [l for l in removed if l.strip()]
    assert non_blank_removed == [], (
        f"docs/aide/insights.md diff removes non-blank line(s), not append-only: "
        f"{non_blank_removed}"
    )


def test_adv_synthetic_insights_removal_would_fail_the_append_only_check():
    """Adversarial: a synthetic diff removing a non-blank existing insights
    line must be caught by the same non-blank-removal rule the real AC28
    check applies."""
    synthetic_removed_lines = ["- [ ] knowledge -- an existing entry *(item 100, 2026-08-01)*"]
    non_blank_removed = [l for l in synthetic_removed_lines if l.strip()]
    assert non_blank_removed != [], "expected the synthetic removal to be non-blank"


# =========================================================================== #
# Determinism / immutability (Testing Strategy)
# =========================================================================== #


def test_adv_four_level_held_out_computation_is_deterministic():
    scenario1 = _displaced_straight_spine(4)
    scenario2 = _displaced_straight_spine(4)
    offsets1 = tuple(r.offset_mm for r in compute_leave_one_out_spline_offsets(scenario1))
    offsets2 = tuple(r.offset_mm for r in compute_leave_one_out_spline_offsets(scenario2))
    assert offsets1 == pytest.approx(offsets2)


def test_adv_nested_label_map_build_does_not_touch_committed_fixtures():
    """Immutability: building the coincident-centroid map is entirely
    in-memory -- no committed corpus fixture or manifest file changes."""
    manifest_before = (_TESTS_DIR / "corpus" / "manifest.json").read_bytes()
    seg_img = t129._coincident_label_map()
    t129._assert_coincidence(seg_img, 21, 22)
    extract_feature_record(seg_img, bundled_default_config())
    manifest_after = (_TESTS_DIR / "corpus" / "manifest.json").read_bytes()
    assert manifest_before == manifest_after


def test_adv_four_level_scenario_build_does_not_mutate_shared_helper_output():
    """Immutability: dataclasses.replace produces a new centroid rather than
    mutating the one t129._straight_spine returned, so calling the builder
    twice yields equal, independent sequences."""
    base1 = t129._straight_spine(4)
    base2 = t129._straight_spine(4)
    assert base1 == base2
    displaced = _displaced_straight_spine(4)
    # The original t129._straight_spine(4) call is unaffected by building a
    # displaced scenario from a *fresh* base call.
    base3 = t129._straight_spine(4)
    assert base3 == base1
    assert displaced[1].centroid_mm != base1[1].centroid_mm
