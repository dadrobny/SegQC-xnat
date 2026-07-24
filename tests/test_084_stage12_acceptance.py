"""Stage-12 G3 acceptance module (item 084) -- closes Stage 12.

Quantifies objective G3 (GT segmentations pass QC at a high rate / low
false-positive rate) via the Stage-7 ``segfacet evaluate`` path, and supplies
the machine-checkable evidence + guard that gate flipping the "Real VerSe
GT" row in ``progress.md``'s Environment-Gated Capability Verification
table from Unverified to Verified.

This item adds **no** production code: everything below -- the tiny
importable helpers (``real_verse_cohort_dir``, ``build_gt_pass_manifest``,
``g3_verification_record``, ``may_mark_verified``) and the tests -- lives
entirely in this acceptance module (mirroring item 075's importable
``stage10_acceptance_record`` pattern).

Covers Acceptance Criteria AC1-AC11:

- AC1: the module exists and exposes the four callables.
- AC2: ``build_gt_pass_manifest`` produces an evaluate-shape expected-pass
  cohort from GT segs (GT-as-candidate).
- AC3/AC4: evaluating the synthetic stand-in cohort exits 0, writes a
  well-formed ``eval_report.json`` whose FPR is ``0.0`` for the clean
  self-vs-self cohort.
- AC5/AC6: the real-VerSe clause is a GENUINE skip (never xfail, never a
  vacuous pass) when ``SEGFACET_VERSE_COHORT`` is unset or points nowhere.
- AC7-AC10: the G3 verification-evidence record shape, the
  ``may_mark_verified`` guard truth-table, the synthetic-only run's
  self-reported non-verified record, and FPR consistency with the report.
- AC11: no production code / new dependency is introduced by this item.

Adversarial / edge cases:
- Nonexistent / empty ``SEGFACET_VERSE_COHORT`` values.
- ``build_gt_pass_manifest`` over an empty cohort dir yields an empty
  ``cases`` list, no traceback.
- ``may_mark_verified`` non-vacuity: a real cohort with a missing
  ``build_date`` (and vice-versa) still refuses to verify.
- FPR is never ``None`` for the deliberately non-empty stand-in cohort.
- Determinism across two evaluate runs of the same stand-in manifest.
- ``SEGFACET_VERSE_COHORT`` env hygiene after monkeypatch teardown.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

import nibabel as nib
import pytest

from segfacet.cli import main as segfacet_main
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.intensity import paint_clean_scan

# =========================================================================== #
# Public helpers (test-side only -- no src/segfacet/** change, item 084 A1)
# =========================================================================== #


def real_verse_cohort_dir() -> Optional[pathlib.Path]:
    """Return the real VerSe GT cohort dir from ``SEGFACET_VERSE_COHORT`` iff the
    env var is set AND the directory exists; else ``None``. The single
    runtime gate for the real-VerSe clause (analogue of ``cupy_available()``/
    ``_docker_available()``)."""
    raw = os.environ.get("SEGFACET_VERSE_COHORT")
    if not raw:
        return None
    candidate = pathlib.Path(raw)
    if not candidate.is_dir():
        return None
    return candidate


def build_gt_pass_manifest(
    cohort_dir, out_dir, *, seg_suffix: str = "_seg-vert_msk.nii.gz"
) -> pathlib.Path:
    """Turn a directory of GT vertebra-mask segs into an ``evaluate``-shape
    manifest of expected-pass cases (``candidate == gt``,
    ``expected_verdict == "pass"``), written into ``out_dir`` with gt/
    candidate paths relative to the manifest's own dir. Returns the
    manifest path."""
    cohort_dir = pathlib.Path(cohort_dir)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    for seg_path in sorted(cohort_dir.glob(f"*{seg_suffix}")):
        case_id = seg_path.name[: -len(seg_suffix)]
        rel = os.path.relpath(seg_path, start=out_dir)
        rel = rel.replace(os.sep, "/")
        cases.append(
            {
                "case_id": case_id,
                "gt": rel,
                "candidate": rel,
                "expected": {"expected_verdict": "pass"},
            }
        )

    manifest = {"manifest_version": 1, "cases": cases}
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def g3_verification_record(
    *,
    real_cohort_present: bool,
    cohort_id: Optional[str],
    build_date: Optional[str],
    false_positive_rate: Optional[float],
) -> dict:
    """Return a JSON-native G3 verification-evidence record. ``verified`` is
    ``True`` only when ``may_mark_verified`` accepts the record -- never
    inferred from a synthetic-only run."""
    record = {
        "real_verse_cohort_present": bool(real_cohort_present),
        "cohort_id": cohort_id,
        "build_date": build_date,
        "false_positive_rate": false_positive_rate,
    }
    record["verified"] = may_mark_verified(record)
    return record


def may_mark_verified(record: dict) -> bool:
    """The guard: True iff ``record["real_verse_cohort_present"]`` AND a
    non-empty ``record["cohort_id"]`` AND a non-empty
    ``record["build_date"]``. Any synthetic-only record -> False, so the
    "Real VerSe GT" row can never be flipped Verified from a synthetic run."""
    return bool(
        record.get("real_verse_cohort_present")
        and record.get("cohort_id")
        and record.get("build_date")
    )


# =========================================================================== #
# Genuine-skip gate for the real-VerSe clause (AC5/AC6, item 069 precedent)
# =========================================================================== #

requires_verse = pytest.mark.skipif(
    real_verse_cohort_dir() is None,
    reason="real VerSe GT cohort not mounted (set SEGFACET_VERSE_COHORT)",
)


# =========================================================================== #
# Fixture helper: the synthetic VerSe-shaped stand-in cohort
# =========================================================================== #

_STANDIN_SEG_SUFFIX = "_seg-vert_msk.nii.gz"


def _build_standin_cohort(dest_dir: pathlib.Path, n: int = 2) -> pathlib.Path:
    """Write a tiny (default 2-subject) VerSe-shaped stand-in cohort:
    ``build_clean_spine`` (L1-L5) + ``paint_clean_scan`` sibling scans,
    saved as ``<id>_seg-vert_msk.nii.gz`` + ``<id>_scan.nii.gz`` pairs --
    the same shape items 082/083 use. No real VerSe data."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        spine = build_clean_spine(
            levels=("L1", "L2", "L3", "L4", "L5"),
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        scan_img = paint_clean_scan(spine.seg_img, seed=i)
        subject_id = f"verse-standin-{i:03d}"
        nib.save(spine.seg_img, str(dest_dir / f"{subject_id}{_STANDIN_SEG_SUFFIX}"))
        nib.save(scan_img, str(dest_dir / f"{subject_id}_scan.nii.gz"))
    return dest_dir


def _run_evaluate(manifest_path, out_dir, *, cohort_id="verse-standin", build_date="2026-07-15"):
    return segfacet_main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--cohort-id",
            cohort_id,
            "--build-date",
            build_date,
        ]
    )


def _read_report(out_dir: pathlib.Path) -> dict:
    return json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))


# =========================================================================== #
# AC1: module + importable helpers present
# =========================================================================== #


def test_ac1_module_exposes_callable_helpers():
    assert callable(real_verse_cohort_dir)
    assert callable(build_gt_pass_manifest)
    assert callable(g3_verification_record)
    assert callable(may_mark_verified)


# =========================================================================== #
# AC2: build_gt_pass_manifest produces an evaluate-shape expected-pass cohort
# =========================================================================== #


def test_ac2_build_gt_pass_manifest_produces_expected_pass_cohort(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    out_dir = tmp_path / "manifest_out"

    manifest_path = build_gt_pass_manifest(cohort_dir, out_dir)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 1
    assert len(manifest["cases"]) >= 1

    manifest_dir = manifest_path.parent
    for case in manifest["cases"]:
        assert case["expected"]["expected_verdict"] == "pass"
        gt_path = (manifest_dir / case["gt"]).resolve()
        candidate_path = (manifest_dir / case["candidate"]).resolve()
        assert gt_path.is_file()
        assert candidate_path.is_file()
        assert gt_path.read_bytes() == candidate_path.read_bytes()


# =========================================================================== #
# AC3/AC4: synthetic evaluate -> FPR path (CI, unconditional)
# =========================================================================== #


def test_ac3_evaluate_exits_zero_and_writes_well_formed_report(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")
    out_dir = tmp_path / "out"

    exit_code = _run_evaluate(manifest_path, out_dir)

    assert exit_code == 0
    report_path = out_dir / "eval_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"]
    assert "provenance" in report
    assert "metrics" in report


def test_ac4_report_fpr_is_well_formed_and_zero_for_clean_standin(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")
    out_dir = tmp_path / "out"

    exit_code = _run_evaluate(manifest_path, out_dir)
    assert exit_code == 0

    report = _read_report(out_dir)
    metrics = report["metrics"]
    fpr = metrics["false_positive_rate"]
    assert isinstance(fpr, float)
    assert 0.0 <= fpr <= 1.0
    assert fpr == 0.0
    assert isinstance(metrics["per_mode"], list)
    assert metrics["per_mode"] == []


# =========================================================================== #
# AC5: the real-VerSe clause is a GENUINE skip (structural proof)
# =========================================================================== #


def test_ac5_requires_verse_marker_is_a_genuine_skipif():
    assert requires_verse.mark.name == "skipif"
    condition = requires_verse.mark.args[0]
    assert isinstance(condition, bool)
    # On this data-absent host (no SEGFACET_VERSE_COHORT mounted in CI/dev) the
    # condition must be True so the gated test actually skips -- never xfail,
    # never an unconditional pass.
    assert condition is True


@requires_verse
def test_ac5_real_cohort_evaluation_runs_only_when_mounted(tmp_path):
    """Positive counterpart: on a data-holding host this exercises the real
    cohort and asserts the record can be verified. Skips cleanly everywhere
    else (proven structurally above)."""
    cohort_dir = real_verse_cohort_dir()
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")
    out_dir = tmp_path / "out"

    exit_code = _run_evaluate(
        manifest_path, out_dir, cohort_id="verse-v1", build_date="2026-07-15"
    )
    assert exit_code == 0

    report = _read_report(out_dir)
    fpr = report["metrics"]["false_positive_rate"]
    assert isinstance(fpr, float)
    assert 0.0 <= fpr <= 1.0

    record = g3_verification_record(
        real_cohort_present=True,
        cohort_id="verse-v1",
        build_date="2026-07-15",
        false_positive_rate=fpr,
    )
    assert record["verified"] is True
    assert may_mark_verified(record) is True


# =========================================================================== #
# AC6: real_verse_cohort_dir() env behaviour
# =========================================================================== #


def test_ac6_returns_none_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)
    assert real_verse_cohort_dir() is None


def test_ac6_returns_none_when_env_var_points_to_nonexistent_path(monkeypatch, tmp_path):
    nonexistent = tmp_path / "no-such-verse-dir"
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(nonexistent))
    assert real_verse_cohort_dir() is None


def test_ac6_returns_path_when_env_var_points_to_existing_dir(monkeypatch, tmp_path):
    existing = tmp_path / "verse-cohort"
    existing.mkdir()
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(existing))
    result = real_verse_cohort_dir()
    assert result is not None
    assert pathlib.Path(result).resolve() == existing.resolve()


# =========================================================================== #
# AC7: g3_verification_record schema
# =========================================================================== #


def test_ac7_record_has_exact_key_set_and_json_native_types():
    record = g3_verification_record(
        real_cohort_present=False,
        cohort_id=None,
        build_date=None,
        false_positive_rate=None,
    )

    assert set(record.keys()) == {
        "real_verse_cohort_present",
        "cohort_id",
        "build_date",
        "false_positive_rate",
        "verified",
    }
    assert isinstance(record["real_verse_cohort_present"], bool)
    assert record["cohort_id"] is None
    assert record["build_date"] is None
    assert record["false_positive_rate"] is None
    assert isinstance(record["verified"], bool)

    round_tripped = json.loads(json.dumps(record))
    assert round_tripped == record


def test_ac7_record_json_round_trip_with_real_values():
    record = g3_verification_record(
        real_cohort_present=True,
        cohort_id="verse-v1",
        build_date="2026-07-15",
        false_positive_rate=0.0,
    )
    round_tripped = json.loads(json.dumps(record))
    assert round_tripped == record
    assert isinstance(record["false_positive_rate"], float)


# =========================================================================== #
# AC8: may_mark_verified truth-table (parametrised, non-vacuous guard)
# =========================================================================== #


@pytest.mark.parametrize(
    "present, cohort_id, build_date, expected",
    [
        pytest.param(True, "verse-v1", "2026-07-15", True, id="fully-provenanced"),
        pytest.param(False, "verse-v1", "2026-07-15", False, id="no-real-cohort"),
        pytest.param(True, "", "2026-07-15", False, id="empty-cohort-id"),
        pytest.param(True, None, "2026-07-15", False, id="none-cohort-id"),
        pytest.param(True, "verse-v1", "", False, id="empty-build-date"),
        pytest.param(True, "verse-v1", None, False, id="none-build-date"),
        pytest.param(False, "", "", False, id="all-falsy"),
    ],
)
def test_ac8_may_mark_verified_truth_table(present, cohort_id, build_date, expected):
    record = {
        "real_verse_cohort_present": present,
        "cohort_id": cohort_id,
        "build_date": build_date,
        "false_positive_rate": 0.0,
        "verified": None,  # not consulted by the guard
    }
    assert may_mark_verified(record) is expected


def test_ac8_guard_non_vacuity_missing_build_date_with_real_cohort():
    record = {
        "real_verse_cohort_present": True,
        "cohort_id": "verse-v1",
        "build_date": None,
        "false_positive_rate": 0.0,
    }
    assert may_mark_verified(record) is False


def test_ac8_guard_non_vacuity_missing_cohort_id_with_real_cohort():
    record = {
        "real_verse_cohort_present": True,
        "cohort_id": None,
        "build_date": "2026-07-15",
        "false_positive_rate": 0.0,
    }
    assert may_mark_verified(record) is False


# =========================================================================== #
# AC9: synthetic-only run yields a non-verified, self-reported record
# =========================================================================== #


def test_ac9_synthetic_only_record_is_non_verified_and_self_reported(capsys):
    record = g3_verification_record(
        real_cohort_present=False,
        cohort_id=None,
        build_date=None,
        false_positive_rate=0.0,
    )

    assert record["real_verse_cohort_present"] is False
    assert record["verified"] is False
    assert may_mark_verified(record) is False

    print(record)
    captured = capsys.readouterr()
    assert "real_verse_cohort_present" in captured.out
    assert "False" in captured.out


# =========================================================================== #
# AC10: record's FPR is consistent with the AC3/AC4 report's FPR
# =========================================================================== #


def test_ac10_record_fpr_matches_report_fpr(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")
    out_dir = tmp_path / "out"

    exit_code = _run_evaluate(manifest_path, out_dir)
    assert exit_code == 0
    report = _read_report(out_dir)
    report_fpr = report["metrics"]["false_positive_rate"]

    record = g3_verification_record(
        real_cohort_present=False,
        cohort_id=None,
        build_date=None,
        false_positive_rate=report_fpr,
    )
    assert record["false_positive_rate"] == report_fpr


# =========================================================================== #
# AC11: scope / regression guard -- no production code, no new dependency
# =========================================================================== #


def test_ac11_no_new_dependency():
    """No new core dependency was introduced by item 084.

    The original AC11 also diffed this branch against ``main`` to prove item
    084 added no ``src/segfacet/**``/``scripts/**`` file -- a one-time proof that
    was true at merge time and reviewed then. Left as a permanent check it is
    unsound: any *later* item that legitimately adds source under
    ``src/segfacet/`` (e.g. item 071's ``backend.py``) makes this branch's diff
    against a moving ``main`` include that path, failing a guard about item
    084's own historical scope rather than the current branch's. Narrowed to
    the timeless part -- the dependency set -- which item 084 also never
    changed and which remains meaningful to re-check on any branch."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    import re

    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", pyproject_text, re.DOTALL)
    assert match is not None
    deps_block = match.group(1)
    dep_names = [
        line.strip().strip(",").strip('"').split(">=")[0].split("==")[0]
        for line in deps_block.splitlines()
        if line.strip()
    ]
    expected_deps = {"numpy", "scipy", "scikit-image", "nibabel", "PyYAML", "jsonschema"}
    assert set(dep_names) == expected_deps


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_cohort_dir_yields_empty_cases_no_traceback(tmp_path):
    empty_cohort = tmp_path / "empty_cohort"
    empty_cohort.mkdir()
    out_dir = tmp_path / "manifest_out"

    manifest_path = build_gt_pass_manifest(empty_cohort, out_dir)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["cases"] == []


def test_adv_fpr_is_not_none_for_nonempty_standin_cohort(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")
    out_dir = tmp_path / "out"

    exit_code = _run_evaluate(manifest_path, out_dir)
    assert exit_code == 0
    report = _read_report(out_dir)
    assert report["metrics"]["false_positive_rate"] is not None


def test_adv_determinism_two_evaluate_runs_produce_equal_fpr(tmp_path):
    cohort_dir = _build_standin_cohort(tmp_path / "cohort")
    manifest_path = build_gt_pass_manifest(cohort_dir, tmp_path / "manifest_out")

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    assert _run_evaluate(manifest_path, out_a) == 0
    assert _run_evaluate(manifest_path, out_b) == 0

    fpr_a = _read_report(out_a)["metrics"]["false_positive_rate"]
    fpr_b = _read_report(out_b)["metrics"]["false_positive_rate"]
    assert fpr_a == fpr_b


def test_adv_env_var_hygiene_after_monkeypatch_teardown(monkeypatch, tmp_path):
    existing = tmp_path / "verse-cohort"
    existing.mkdir()
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(existing))
    assert real_verse_cohort_dir() is not None
    monkeypatch.undo()
    assert "SEGFACET_VERSE_COHORT" not in os.environ or os.environ.get(
        "SEGFACET_VERSE_COHORT"
    ) != str(existing)
