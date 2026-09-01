"""Tests for item 083 -- one-command reference-refresh wrapper
(``scripts/refresh_reference.py``).

Covers Acceptance Criteria AC1-AC13:

- AC1: the wrapper exists with a callable ``main(argv) -> int``.
- AC2-AC6: the synthetic refresh path (no ``--verse-cohort``) -- exit 0, a
  well-formed ``reference_default.json``, a self-vs-self eval manifest,
  a well-formed ``eval_report.json`` with FPR in [0, 1], and a
  machine-checkable structured summary written + returned.
- AC7-AC9 (the real-VerSe skip/build steps this module used to pin) and AC10
  (the stand-in-cohort verse-build run): **retired 2026-08-31, item 133.**
  ``refresh_reference.py --verse-cohort`` no longer delegates to a real-VerSe
  build at all -- the flag is rejected outright with exit code 2 and a
  pointer to ``scripts/rebuild_verse_reference.py`` (item 123's dedicated,
  working real-cohort tool). The five tests that pinned the old genuine-skip
  / stand-in-build behaviour (``test_ac7_verse_build_is_genuine_skip_without_cohort``,
  ``test_ac9_nonexistent_verse_cohort_is_absent_not_a_crash``,
  ``test_ac10_verse_build_runs_with_standin_cohort``,
  ``test_adversarial_empty_but_present_verse_cohort_no_crash``, and the
  ``--verse-cohort`` half of ``test_ac12_writes_only_into_out_dir``) and the
  ``_build_standin_verse_cohort`` helper they used are deleted here, not
  rewritten -- the retirement they described is now this module's owner's
  responsibility, not item 083's. See
  ``tests/test_133_tptbox_pin_and_verse_retirement.py`` (AC8/AC9) for the
  retired-mode coverage.
- AC11-AC13: determinism, output containment under ``--out``, and
  self-containment (no ``tests/`` coupling).

Adversarial / edge-case scenarios included:
- ``--out`` under a not-yet-existing parent: created with parents.
- Idempotent re-run into the same ``--out``: overwrites cleanly, equal
  summary.
- Manifest ``gt``/``candidate`` paths are relative to the manifest's own
  directory (item 057's resolution rule).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from segfacet.reference import default_artifact_path, load_artifact

# --------------------------------------------------------------------------- #
# Module loader (mirrors tests/test_aide_status_report.py's by-path pattern)
# --------------------------------------------------------------------------- #

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refresh_reference.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("refresh_reference", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read_summary(out: Path) -> dict:
    return json.loads((out / "refresh_summary.json").read_text(encoding="utf-8"))


def _no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def _capture_main(rr, argv):
    """Run main(argv), capturing combined stdout+stderr text; return (rc, text)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = rr.main(argv)
    return rc, out_buf.getvalue() + err_buf.getvalue()


# =========================================================================== #
# Group A -- presence/shape (AC1)
# =========================================================================== #


def test_ac1_wrapper_loads_with_callable_main(tmp_path):
    rr = _load_wrapper()
    assert callable(rr.main)
    rc = rr.main(["--out", str(tmp_path / "out")])
    assert isinstance(rc, int)


# =========================================================================== #
# Group B -- synthetic path (AC2-AC6)
# =========================================================================== #


def test_ac2_no_verse_cohort_exits_zero(tmp_path):
    rr = _load_wrapper()
    rc = rr.main(["--out", str(tmp_path / "out")])
    assert rc == 0


def test_ac3_rebuilds_well_formed_synthetic_default_artifact(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rr.main(["--out", str(out)])

    dist = load_artifact(out / "reference_default.json")
    assert dist.schema_version
    assert any(dist.levels.values())
    first_level_strata = next(iter(dist.levels.values()))
    first_stratum = next(iter(first_level_strata.values()))
    assert len(first_stratum.feature_stats) >= 1


def test_ac4_synthesizes_self_vs_self_eval_cohort(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rr.main(["--out", str(out)])

    manifest_path = out / "eval_cohort" / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 1
    assert len(manifest["cases"]) >= 1

    base_dir = manifest_path.parent
    found_self_vs_self = False
    for case in manifest["cases"]:
        gt_path = (base_dir / case["gt"]).resolve()
        cand_path = (base_dir / case["candidate"]).resolve()
        assert gt_path.is_file()
        assert cand_path.is_file()
        if gt_path.read_bytes() == cand_path.read_bytes():
            if case["expected"]["expected_verdict"] == "pass":
                found_self_vs_self = True
    assert found_self_vs_self


def test_ac5_eval_report_has_fpr_in_range(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rr.main(["--out", str(out)])

    eval_reports = list(out.rglob("eval_report.json"))
    assert len(eval_reports) >= 1
    report = json.loads(eval_reports[0].read_text(encoding="utf-8"))
    assert "schema_version" in report
    assert "metrics" in report
    fpr = report["metrics"]["false_positive_rate"]
    assert isinstance(fpr, float)
    assert 0.0 <= fpr <= 1.0
    assert fpr == 0.0  # self-vs-self clean cohort: no false positives


def test_ac6_structured_summary_written_and_returned_match(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    returned = rr.run_refresh(out)

    assert isinstance(returned, dict)
    assert "steps" in returned

    rr.main(["--out", str(tmp_path / "out2")])
    summary_path = tmp_path / "out2" / "refresh_summary.json"
    assert summary_path.is_file()
    written = json.loads(summary_path.read_text(encoding="utf-8"))

    for step in returned["steps"]:
        assert set(("name", "status", "reason")) <= set(step.keys())
        assert step["status"] in {"ran", "skipped", "failed"}
        assert isinstance(step["reason"], str)

    written_pairs = [(s["name"], s["status"]) for s in written["steps"]]
    returned_pairs = [(s["name"], s["status"]) for s in rr.run_refresh(tmp_path / "out3")["steps"]]
    assert written_pairs == returned_pairs


# =========================================================================== #
# Group C -- AC8 (the synthetic path is unaffected by real-VerSe absence)
# =========================================================================== #


def test_ac8_skip_does_not_abort_synthetic_path(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])
    summary = _read_summary(out)

    steps_by_name = {s["name"]: s for s in summary["steps"]}
    for name in (rr.STEP_SYNTH_REBUILD, rr.STEP_EVAL_COHORT, rr.STEP_SYNTH_EVALUATE):
        assert steps_by_name[name]["status"] == "ran"
    assert rc == 0


# =========================================================================== #
# Group E -- determinism, containment, self-containment (AC11-AC13)
# =========================================================================== #


def test_ac11_deterministic_across_two_out_dirs(tmp_path):
    rr = _load_wrapper()
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    rr.main(["--out", str(out_a)])
    rr.main(["--out", str(out_b)])

    summary_a = _read_summary(out_a)
    summary_b = _read_summary(out_b)
    pairs_a = [(s["name"], s["status"]) for s in summary_a["steps"]]
    pairs_b = [(s["name"], s["status"]) for s in summary_b["steps"]]
    assert pairs_a == pairs_b

    ref_a = (out_a / "reference_default.json").read_bytes()
    ref_b = (out_b / "reference_default.json").read_bytes()
    assert ref_a == ref_b

    manifest_a = json.loads((out_a / "eval_cohort" / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((out_b / "eval_cohort" / "manifest.json").read_text(encoding="utf-8"))
    cases_a = [(c["case_id"], c["expected"]) for c in manifest_a["cases"]]
    cases_b = [(c["case_id"], c["expected"]) for c in manifest_b["cases"]]
    assert cases_a == cases_b


def test_ac12_writes_only_into_out_dir(tmp_path):
    rr = _load_wrapper()
    default_path = default_artifact_path()
    before = default_path.read_bytes()

    out = tmp_path / "out"
    rr.main(["--out", str(out)])

    after = default_path.read_bytes()
    assert before == after

    # Every path recorded as an "output" by the run must live under --out.
    summary = _read_summary(out)
    out_resolved = out.resolve()
    for step in summary["steps"]:
        output = step.get("output")
        if output:
            resolved = Path(output).resolve()
            assert out_resolved in resolved.parents or resolved == out_resolved


def test_ac13_no_tests_corpus_or_tests_package_coupling():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "tests/corpus" not in source
    assert "import tests" not in source
    assert "from tests" not in source


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_out_dir_under_not_yet_existing_parent(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "brand_new_parent" / "nested" / "out"
    assert not out.parent.exists()

    rc = rr.main(["--out", str(out)])

    assert rc == 0
    assert out.is_dir()
    assert (out / "reference_default.json").is_file()
    assert (out / "refresh_summary.json").is_file()


def test_adversarial_idempotent_rerun_into_same_out(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rr.main(["--out", str(out)])
    summary_1 = _read_summary(out)

    rc2 = rr.main(["--out", str(out)])
    summary_2 = _read_summary(out)

    assert rc2 == 0
    pairs_1 = [(s["name"], s["status"]) for s in summary_1["steps"]]
    pairs_2 = [(s["name"], s["status"]) for s in summary_2["steps"]]
    assert pairs_1 == pairs_2


def test_adversarial_manifest_paths_relative_to_manifest_dir(tmp_path):
    rr = _load_wrapper()
    out = tmp_path / "out"
    rr.main(["--out", str(out)])

    manifest_path = out / "eval_cohort" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        gt_value = case["gt"]
        candidate_value = case["candidate"]
        # Not absolute -- stored relative to the manifest's own directory so
        # the cohort directory is relocatable (item 057's resolution rule).
        assert not Path(gt_value).is_absolute()
        assert not Path(candidate_value).is_absolute()
        assert (manifest_path.parent / gt_value).resolve().is_file()
        assert (manifest_path.parent / candidate_value).resolve().is_file()
