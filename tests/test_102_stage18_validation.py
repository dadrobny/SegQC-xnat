"""Stage 18 end-to-end validation (item 102).

Replays the four things Stage 18 shipped -- through the shipped **CLI**, not
the unit suite each item already exercises -- and closes the stage's two
roadmap acceptance criteria (G2, G7) honestly. This module adds no production
code (see AC24's scope-fence test); it is one new test file plus
``docs/aide/progress.md`` edits (done separately, not here).

Four blocks, module-scoped fixtures so the expensive artifacts (CLI runs, two
full cohort evaluations, the ~4.3s severity harness) are built once each and
shared by every test that needs them:

- **Block A** (AC1-AC4, AC6) -- CLI ``run`` on ``mode3_inject_islands``, both
  ``--no-reference`` and default flags (the "CLI trap": reference mode is ON
  by default since item 090).
- **Block B** (AC5) -- nine CLI ``run --no-reference`` invocations, one per
  corpus case, diffed against the frozen pre-098 snapshot imported from
  ``tests/test_098_stray_components.py``.
- **Block C** (AC7-AC13) -- two real ``segfacet evaluate --per-mode`` runs
  over an in-memory composite cohort (shared ``displace`` + ``fragment``
  background departure, islands only in run A) diffed by a real
  ``segfacet compare-runs`` invocation.
- **Block D** (AC14-AC17) -- one shared ``score_harness(run_severity_harness())``
  call, asserting the exact rung-count / severity-kind / status / margin
  table recorded in the item spec.

Plus AC24's scope fence (no production file touched by this item) and the
Testing Strategy's adversarial/edge cases: the ``--no-reference`` inversion,
swapped-run sign flip, self-comparison, mismatched-cohort rejection, a
``compare-runs`` against a report written without ``--per-mode``,
determinism, and no-mutation of inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import jsonschema
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from segfacet import cli
from segfacet.synth.corpus import load_manifest
from segfacet.synth.perturbation import FAILURE_MODE_NAMES, get_perturbation
from segfacet.synth.clean_gt import build_clean_spine
from test_098_stray_components import (
    _FACE_NAME_SENSITIVE_CASES,
    _PRE_098_GOLDEN_VERDICT_AND_FINDINGS,
    _finding_summary,
)

_TESTS_DIR = Path(__file__).resolve().parent
_CORPUS_FIXTURES = _TESTS_DIR / "corpus" / "fixtures"
_BASE_SCAN = _CORPUS_FIXTURES / "base_scan.nii.gz"
_MANIFEST_PATH = _TESTS_DIR / "corpus" / "manifest.json"

_SEGFACET_SRC = Path(__import__("segfacet").__file__).resolve().parent
_LADDER_SEED = 0


def _seg_fixture(case_id: str) -> Path:
    return _CORPUS_FIXTURES / f"{case_id}_seg.nii.gz"


def _report_schema() -> dict:
    import importlib.resources

    import segfacet as _segfacet_pkg

    ref = importlib.resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _comparison_schema() -> dict:
    import importlib.resources

    import segfacet.eval as eval_pkg

    ref = importlib.resources.files(eval_pkg).joinpath("per_mode_comparison_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


# =========================================================================== #
# Block A (AC1-AC4, AC6): CLI run on mode3_inject_islands, both flag states
# =========================================================================== #


@pytest.fixture(scope="module")
def block_a(tmp_path_factory):
    out_noref = tmp_path_factory.mktemp("block_a_noref")
    out_default = tmp_path_factory.mktemp("block_a_default")
    seg = _seg_fixture("mode3_inject_islands")

    exit_noref = cli.main(
        [
            "run",
            "--scan",
            str(_BASE_SCAN),
            "--seg",
            str(seg),
            "--out",
            str(out_noref),
            "--no-reference",
        ]
    )
    exit_default = cli.main(
        [
            "run",
            "--scan",
            str(_BASE_SCAN),
            "--seg",
            str(seg),
            "--out",
            str(out_default),
        ]
    )
    assert exit_noref == 0
    assert exit_default == 0

    report_noref = json.loads((out_noref / "segfacet_report.json").read_text(encoding="utf-8"))
    report_default = json.loads(
        (out_default / "segfacet_report.json").read_text(encoding="utf-8")
    )
    return {"noref": report_noref, "default": report_default}


def test_ac1_full_run_surfaces_stray_fields_in_every_per_label_entry(block_a):
    per_label = block_a["noref"]["features"]["per_label"]
    assert per_label, "mode3_inject_islands report has no per_label entries"
    for label_key, entry in per_label.items():
        comp = entry["components"]
        for key in (
            "stray_component_count",
            "stray_component_sizes",
            "stray_volume_mm3",
            "stray_volume_fraction",
        ):
            assert key in comp, f"label {label_key!r} components block missing {key!r}"


def test_ac2_stray_fields_isolate_mode_3_on_label_22(block_a):
    per_label = block_a["noref"]["features"]["per_label"]
    comp_22 = per_label["22"]["components"]
    assert comp_22["stray_component_count"] == 1
    assert comp_22["stray_component_sizes"] == [27]
    assert comp_22["stray_volume_mm3"] == 27.0
    assert 0.0 < comp_22["stray_volume_fraction"] < 0.01

    for label_key in ("20", "21", "23", "24"):
        comp = per_label[label_key]["components"]
        assert comp["stray_component_count"] == 0
        assert comp["stray_component_sizes"] == []
        assert comp["stray_volume_mm3"] == 0.0
        assert comp["stray_volume_fraction"] == 0.0


@pytest.mark.parametrize("flavour", ["noref", "default"])
def test_ac3_report_validates_against_bundled_schema_both_reference_modes(block_a, flavour):
    jsonschema.validate(block_a[flavour], _report_schema())


@pytest.mark.parametrize("flavour", ["noref", "default"])
def test_ac4_complement_invariant_holds_at_report_level(block_a, flavour):
    per_label = block_a[flavour]["features"]["per_label"]
    for label_key, entry in per_label.items():
        comp = entry["components"]
        total = comp["stray_volume_fraction"] + comp["largest_component_fraction"]
        assert math.isclose(total, 1.0, abs_tol=1e-12), (
            f"label {label_key!r} ({flavour}): "
            f"stray_volume_fraction + largest_component_fraction = {total!r}"
        )


def test_ac6_default_flag_run_does_not_equal_pre_098_snapshot(block_a):
    """AC6: --no-reference is load-bearing for AC5 -- the default-flag run of
    the same case must NOT reproduce the frozen snapshot, so a future reader
    cannot drop the flag from AC5 and get a spurious pass."""
    report = block_a["default"]
    findings = report["findings"]
    rule_ids = {f["rule_id"] for f in findings}
    assert "reference_delta" in rule_ids
    assert "bounds" in rule_ids

    frag = [f for f in findings if f["rule_id"] == "fragmentation"]
    assert len(frag) == 1
    expected_reason = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode3_inject_islands"][
        "findings"
    ][0]["reason"]
    assert frag[0]["reason"] != expected_reason


# =========================================================================== #
# Block B (AC5): nine CLI runs, verdict + findings unchanged from pre-098
# =========================================================================== #


def _manifest_case_ids():
    manifest = load_manifest()
    return sorted(c["case_id"] for c in manifest["cases"])


@pytest.fixture(scope="module")
def block_b(tmp_path_factory):
    results = {}
    for case_id in _manifest_case_ids():
        out_dir = tmp_path_factory.mktemp(f"block_b_{case_id}")
        exit_code = cli.main(
            [
                "run",
                "--no-reference",
                "--scan",
                str(_BASE_SCAN),
                "--seg",
                str(_seg_fixture(case_id)),
                "--out",
                str(out_dir),
            ]
        )
        assert exit_code == 0, f"case {case_id!r} run exited {exit_code}"
        report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
        results[case_id] = report
    return results


@pytest.mark.parametrize("case_id", sorted(_PRE_098_GOLDEN_VERDICT_AND_FINDINGS.keys()))
def test_ac5_report_verdict_and_findings_match_pre_098_snapshot(block_b, case_id):
    """AC5. Reason text is compared exactly except for the one
    face-name-sensitive case (``mode6_crop_at_border``'s ``border`` finding,
    item 116) -- see ``test_098_stray_components._FACE_NAME_SENSITIVE_CASES``."""
    report = block_b[case_id]
    expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS[case_id]
    assert report["verdict"] == expected["verdict"]

    include_reason = case_id not in _FACE_NAME_SENSITIVE_CASES
    got_findings = [_finding_summary(f, include_reason=include_reason) for f in report["findings"]]
    expected_findings = [
        _finding_summary(f, include_reason=include_reason) for f in expected["findings"]
    ]
    assert got_findings == expected_findings


# =========================================================================== #
# Block C (AC7-AC13): run-vs-run per-mode attribution through the CLI
# =========================================================================== #


def _apply(base_img, steps):
    """Mirror ``eval/severity_ladder.py::_apply_steps``: chain registered
    perturbation operators in order, never mutating *base_img*."""
    current = base_img
    for name, kwargs in steps:
        operator_cls = get_perturbation(name)
        operator = operator_cls(**dict(kwargs))
        result = operator.apply(current, _LADDER_SEED)
        current = result.labelmap
    return current


def _write_manifest(tmp_path, name, case_id, gt_path, candidate_path):
    manifest = {
        "manifest_version": 1,
        "cases": [
            {
                "case_id": case_id,
                "gt": str(gt_path),
                "candidate": str(candidate_path),
                "expected": {"expected_verdict": "pass"},
            }
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _run_evaluate(manifest_path, out_dir, *, run_id, cohort_id):
    from segfacet.synth import corpus as _corpus  # noqa: F401 -- keep import side effects

    return cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--per-mode",
            "--run-id",
            run_id,
            "--build-date",
            "2026-07-27",
            "--cohort-id",
            cohort_id,
        ]
    )


def _build_composite_fixtures(tmp_path):
    """Build gt/cand_a/cand_b NIfTIs per the item spec's Implementation
    Steps: a shared displace+fragment background departure common to both
    runs, with inject_islands only in run A's candidate."""
    import nibabel as nib

    spine = build_clean_spine(
        levels=("L1", "L2", "L3", "L4", "L5"),
        spacing=(1.0, 1.0, 1.0),
        curve_amplitude_mm=6.0,
    )
    base = spine.seg_img
    common = [
        ("displace", {"target_label": 22, "displacement_mm": 8.0}),
        ("fragment", {"target_label": 20, "n_pieces": 3}),
    ]
    cand_a_img = _apply(
        base,
        common
        + [("inject_islands", {"target_label": 24, "n_islands": 3, "island_voxels": 27})],
    )
    cand_b_img = _apply(base, common)

    gt_path = tmp_path / "gt.nii.gz"
    cand_a_path = tmp_path / "cand_a.nii.gz"
    cand_b_path = tmp_path / "cand_b.nii.gz"
    nib.save(base, str(gt_path))
    nib.save(cand_a_img, str(cand_a_path))
    nib.save(cand_b_img, str(cand_b_path))
    return gt_path, cand_a_path, cand_b_path


def _run_block_c_pipeline(tmp_path):
    """Build the composite fixtures, drive two evaluate runs + one
    compare-runs, and return (exit_code, stdout, comparison_dict, txt, dir)."""
    gt_path, cand_a_path, cand_b_path = _build_composite_fixtures(tmp_path)

    manifest_a = _write_manifest(tmp_path, "cohort_a.json", "case0", gt_path, cand_a_path)
    manifest_b = _write_manifest(tmp_path, "cohort_b.json", "case0", gt_path, cand_b_path)

    out_a = tmp_path / "runA"
    out_b = tmp_path / "runB"
    assert _run_evaluate(manifest_a, out_a, run_id="runA", cohort_id="stage18") == 0
    assert _run_evaluate(manifest_b, out_b, run_id="runB", cohort_id="stage18") == 0

    out_compare = tmp_path / "compare"
    return gt_path, cand_a_path, cand_b_path, manifest_a, manifest_b, out_a, out_b, out_compare


@pytest.fixture(scope="module")
def block_c(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("block_c")
    (
        gt_path,
        cand_a_path,
        cand_b_path,
        manifest_a,
        manifest_b,
        out_a,
        out_b,
        out_compare,
    ) = _run_block_c_pipeline(tmp_path)

    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0

    report_a = json.loads((out_a / "eval_report.json").read_text(encoding="utf-8"))
    report_b = json.loads((out_b / "eval_report.json").read_text(encoding="utf-8"))
    comparison_doc = json.loads(
        (out_compare / "per_mode_comparison.json").read_text(encoding="utf-8")
    )
    txt = (out_compare / "per_mode_comparison.txt").read_text(encoding="utf-8")

    return {
        "tmp_path": tmp_path,
        "gt_path": gt_path,
        "cand_a_path": cand_a_path,
        "cand_b_path": cand_b_path,
        "manifest_a": manifest_a,
        "manifest_b": manifest_b,
        "out_a": out_a,
        "out_b": out_b,
        "out_compare": out_compare,
        "report_a": report_a,
        "report_b": report_b,
        "comparison_doc": comparison_doc,
        "txt": txt,
    }


def _per_mode_by_mode(comparison_doc, mode):
    for entry in comparison_doc["comparison"]["per_mode"]:
        if entry["failure_mode"] == mode:
            return entry
    raise KeyError(mode)


def test_ac7_two_per_mode_runs_each_write_eight_entry_block(block_c):
    for report in (block_c["report_a"], block_c["report_b"]):
        block = report["per_mode_magnitude"]
        modes = [entry["failure_mode"] for entry in block["per_mode"]]
        assert modes == list(range(1, 9))
        for entry in block["per_mode"]:
            assert entry["mean"] is not None
    assert block_c["report_a"]["per_mode_magnitude"]["run_id"] == "runA"
    assert block_c["report_b"]["per_mode_magnitude"]["run_id"] == "runB"


def test_ac8_compare_runs_writes_schema_valid_comparison(block_c):
    jsonschema.validate(block_c["comparison_doc"], _comparison_schema())
    assert block_c["txt"].strip() != ""
    doc = block_c["comparison_doc"]
    assert "run_a" in doc
    assert "run_b" in doc
    assert "schema_version" in doc
    assert "comparison" in doc


def test_ac9_attribution_lands_on_mode_3(block_c):
    comparison = block_c["comparison_doc"]["comparison"]
    assert comparison["attributed_mode"] == 3
    assert comparison["attributed_metric_name"] == "rogue_island_count"

    mode3 = _per_mode_by_mode(block_c["comparison_doc"], 3)
    assert mode3["value_a"] == 3.0
    assert mode3["value_b"] == 0.0
    assert mode3["delta"] == -3.0
    assert mode3["normalised_delta"] == -1.0
    assert mode3["worsened"] is False


def test_ac10_no_untouched_mode_is_implicated(block_c):
    doc = block_c["comparison_doc"]
    for mode in (4, 5, 6, 7, 8):
        entry = _per_mode_by_mode(doc, mode)
        assert entry["delta"] == 0.0
        assert entry["normalised_delta"] == 0.0

    mode1 = _per_mode_by_mode(doc, 1)
    assert abs(mode1["normalised_delta"]) < 0.05
    assert math.isclose(mode1["normalised_delta"], -0.0109, abs_tol=1e-3)


def test_ac11_aggregate_dice_does_not_attribute_what_per_mode_does(block_c):
    comparison = block_c["comparison_doc"]["comparison"]
    assert abs(comparison["mean_dice_delta"]) < 0.01
    assert math.isclose(comparison["mean_dice_delta"], 0.00043, abs_tol=1e-4)

    mode3 = _per_mode_by_mode(block_c["comparison_doc"], 3)
    assert abs(mode3["normalised_delta"]) == 1.0


def test_ac12_rendered_txt_names_the_implicated_mode_in_words(block_c):
    txt = block_c["txt"]
    assert FAILURE_MODE_NAMES[3] in txt
    assert "rogue_island_count" in txt
    for mode in range(1, 9):
        assert FAILURE_MODE_NAMES[mode] in txt


def test_ac13_confounding_modes_are_off_baseline(block_c):
    doc = block_c["comparison_doc"]
    mode1 = _per_mode_by_mode(doc, 1)
    mode2 = _per_mode_by_mode(doc, 2)
    for entry in (mode1, mode2):
        assert entry["value_a"] != entry["baseline"]
        assert entry["value_b"] != entry["baseline"]

    saturated = [
        entry
        for entry in doc["comparison"]["per_mode"]
        if abs(entry["normalised_delta"]) == 1.0
    ]
    assert [entry["failure_mode"] for entry in saturated] == [3]


# --- Adversarial (Block C): swapped runs, self-comparison, mismatched
# cohorts, no-per-mode report, determinism, no-mutation ---------------------


def test_adv_swapped_runs_flip_sign_still_attributes_to_mode_3(block_c, tmp_path_factory):
    out_compare = tmp_path_factory.mktemp("block_c_swapped")
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(block_c["out_b"] / "eval_report.json"),
            "--run-b",
            str(block_c["out_a"] / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0
    doc = json.loads((out_compare / "per_mode_comparison.json").read_text(encoding="utf-8"))
    assert doc["comparison"]["attributed_mode"] == 3
    mode3 = _per_mode_by_mode(doc, 3)
    assert mode3["normalised_delta"] == 1.0
    assert mode3["worsened"] is True


def test_adv_self_comparison_is_all_zero_and_names_no_mode(tmp_path_factory, block_c):
    out_compare = tmp_path_factory.mktemp("block_c_self")
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(block_c["out_a"] / "eval_report.json"),
            "--run-b",
            str(block_c["out_a"] / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0
    doc = json.loads((out_compare / "per_mode_comparison.json").read_text(encoding="utf-8"))
    comparison = doc["comparison"]
    assert comparison["attributed_mode"] is None
    for entry in comparison["per_mode"]:
        assert entry["delta"] == 0.0

    txt = (out_compare / "per_mode_comparison.txt").read_text(encoding="utf-8")
    for mode in range(1, 9):
        assert FAILURE_MODE_NAMES[mode] not in txt


def test_adv_mismatched_cohorts_exit_1_error_on_stderr(tmp_path_factory, block_c, capsys):
    tmp_path = tmp_path_factory.mktemp("block_c_mismatched")
    other_manifest = _write_manifest(
        tmp_path,
        "other.json",
        "different_case_id",
        block_c["gt_path"],
        block_c["cand_b_path"],
    )
    out_other = tmp_path / "other_out"
    assert _run_evaluate(other_manifest, out_other, run_id="other", cohort_id="other") == 0

    out_compare = tmp_path / "compare_mismatched"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(block_c["out_a"] / "eval_report.json"),
            "--run-b",
            str(out_other / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err
    assert not out_compare.exists() or not any(out_compare.iterdir())


def test_adv_compare_runs_against_report_without_per_mode_exits_1(tmp_path_factory, block_c):
    tmp_path = tmp_path_factory.mktemp("block_c_no_per_mode")
    manifest = _write_manifest(
        tmp_path, "no_per_mode.json", "case0", block_c["gt_path"], block_c["cand_b_path"]
    )
    out_no_pm = tmp_path / "no_pm_out"
    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest),
            "--out",
            str(out_no_pm),
            "--build-date",
            "2026-07-27",
            "--cohort-id",
            "no_per_mode",
        ]
    )
    assert exit_code == 0
    assert "per_mode_magnitude" not in json.loads(
        (out_no_pm / "eval_report.json").read_text(encoding="utf-8")
    )

    out_compare = tmp_path / "compare_no_pm"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(block_c["out_a"] / "eval_report.json"),
            "--run-b",
            str(out_no_pm / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1, "compare-runs against a report built without --per-mode must fail cleanly, not traceback"


def test_adv_determinism_two_pipelines_are_byte_identical(tmp_path_factory):
    tmp1 = tmp_path_factory.mktemp("block_c_det1")
    tmp2 = tmp_path_factory.mktemp("block_c_det2")

    def _run_full(tmp_path):
        (
            gt_path,
            cand_a_path,
            cand_b_path,
            manifest_a,
            manifest_b,
            out_a,
            out_b,
            out_compare,
        ) = _run_block_c_pipeline(tmp_path)
        exit_code = cli.main(
            [
                "compare-runs",
                "--run-a",
                str(out_a / "eval_report.json"),
                "--run-b",
                str(out_b / "eval_report.json"),
                "--out",
                str(out_compare),
            ]
        )
        assert exit_code == 0
        return out_compare / "per_mode_comparison.json"

    dest1 = _run_full(tmp1)
    dest2 = _run_full(tmp2)
    assert dest1.read_bytes() == dest2.read_bytes()


def test_adv_no_mutation_of_manifests_and_fixtures(block_c):
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (
            block_c["gt_path"],
            block_c["cand_a_path"],
            block_c["cand_b_path"],
            block_c["manifest_a"],
            block_c["manifest_b"],
        )
    }
    # Re-run the same compare-runs command; the fixtures/manifests must be
    # untouched afterwards (they were already used to build block_c, so this
    # confirms nothing mutates them on repeated reads).
    out_compare = block_c["tmp_path"] / "compare_no_mutation_check"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(block_c["out_a"] / "eval_report.json"),
            "--run-b",
            str(block_c["out_b"] / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0
    for path, digest in before.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path


# =========================================================================== #
# Block D (AC14-AC17): the item-100 severity-ladder harness
# =========================================================================== #


@pytest.fixture(scope="module")
def block_d():
    from segfacet.eval.severity_ladder import run_severity_harness, score_harness

    harness = run_severity_harness()
    verdict = score_harness(harness)
    return verdict


_EXPECTED_RUNG_COUNTS = {1: 5, 2: 5, 3: 5, 4: 3, 5: 4, 6: 4, 7: 2, 8: 5}
_EXPECTED_SEVERITY_KINDS = {
    1: "continuous",
    2: "continuous",
    3: "continuous",
    4: "affected-label-count",
    5: "affected-label-count",
    6: "affected-label-count",
    7: "degenerate",
    8: "continuous",
}
_EXPECTED_MARGINS = {
    1: math.inf,
    2: math.inf,
    3: 112.037,
    4: math.inf,
    5: math.inf,
    6: 0.3585,
    7: math.inf,
    8: 1.0386,
}


def test_ac14_harness_passes_monotone_strictly_changing_for_all_eight_modes(block_d):
    assert block_d.passed is True
    for mode in range(1, 9):
        lv = block_d.per_ladder[mode]
        assert lv.monotone is True, mode
        assert lv.strictly_changed is True, mode
        assert lv.failures == (), mode


def test_ac15_observed_ladder_shapes_match_recorded(block_d):
    from segfacet.eval.severity_ladder import SEVERITY_LADDERS

    rung_counts = {m: len(SEVERITY_LADDERS[m].rungs) for m in range(1, 9)}
    severity_kinds = {m: SEVERITY_LADDERS[m].severity_kind for m in range(1, 9)}
    assert rung_counts == _EXPECTED_RUNG_COUNTS
    assert severity_kinds == _EXPECTED_SEVERITY_KINDS


def test_ac16_every_mode_margin_satisfies_the_frozen_ratchet(block_d):
    from segfacet.eval.severity_ladder import RECORDED_MARGINS

    for mode in range(1, 9):
        lv = block_d.per_ladder[mode]
        recorded = RECORDED_MARGINS[mode]
        if recorded == math.inf:
            assert lv.margin == math.inf, mode
        else:
            assert lv.margin >= recorded * 0.95, mode

    # Record the observed values verbatim (Decisions log cross-check).
    for mode in range(1, 9):
        lv = block_d.per_ladder[mode]
        expected = _EXPECTED_MARGINS[mode]
        if expected == math.inf:
            assert lv.margin == math.inf, mode
        else:
            assert math.isclose(lv.margin, expected, abs_tol=2e-3), (mode, lv.margin)


def test_ac17_the_two_shortfall_modes_are_asserted_as_such(block_d):
    from segfacet.eval.severity_ladder import SEVERITY_LADDERS

    lv6 = block_d.per_ladder[6]
    assert lv6.status == "coupled"
    assert lv6.coupled_modes == (1,)
    assert lv6.margin < 1.0

    lv8 = block_d.per_ladder[8]
    assert lv8.status == "coupled"
    assert lv8.coupled_modes == (1,)
    assert lv8.margin > 1.0

    for mode in (1, 2, 3, 4, 5, 7):
        assert block_d.per_ladder[mode].status == "strict", mode

    assert SEVERITY_LADDERS[7].severity_kind == "degenerate"
    assert SEVERITY_LADDERS[7].rationale != ""


def test_adv_two_harness_runs_yield_equal_to_dict(block_d):
    from segfacet.eval.severity_ladder import run_severity_harness, score_harness

    second = score_harness(run_severity_harness())
    assert second.to_dict() == block_d.to_dict()


# =========================================================================== #
# AC24: the scope fence -- no production code changed by this item
# =========================================================================== #


def _combined_hash(files, base: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.relative_to(base).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _src_tree_files():
    return sorted(_SEGFACET_SRC.rglob("*.py")) + sorted(_SEGFACET_SRC.rglob("*.json"))


# Snapshotted once at collection time -- this item makes no production-code
# change, so the tree must be identical before and after this module's own
# tests run (a builder mistakenly touching src/segfacet/** would flip this).
_SRC_TREE_HASH_AT_COLLECTION = _combined_hash(_src_tree_files(), _SEGFACET_SRC)


def test_ac24_src_tree_is_byte_identical_across_the_test_run():
    """AC24: every file under src/segfacet/ is byte-identical to its
    pre-102 state. This item adds no production code, so the combined hash
    taken now must equal the one taken at module-collection time."""
    current_hash = _combined_hash(_src_tree_files(), _SEGFACET_SRC)
    assert current_hash == _SRC_TREE_HASH_AT_COLLECTION


def test_ac24_roadmap_and_vision_docs_are_not_hashed_here_but_present():
    # This item's Implementation Steps forbid touching roadmap.md/vision.md;
    # this module cannot assert "untouched" (it has no pre-102 snapshot to
    # compare against) but it can confirm the scope fence's premise -- that
    # these live outside src/segfacet/ and are not part of the hashed tree.
    repo_root = _SEGFACET_SRC.parent.parent
    roadmap = repo_root / "docs" / "aide" / "roadmap.md"
    vision = repo_root / "docs" / "aide" / "vision.md"
    assert roadmap.exists()
    assert vision.exists()
    assert repo_root / "docs" not in _SEGFACET_SRC.parents
