"""Stage-17 closing validation (item 097).

Replays Stage 17's use cases end-to-end -- not just the unit-level checks
already covered by items 093 (TPTBox label convention), 094 (TPTBox-backed
orientation-safe ``io.py``), 095 (numpy-major CI matrix), and 096 (run
manifest) -- confirming the four compose correctly. This item adds no new
production code beyond a synthetic-fixture builder and an env-gated test;
every helper lives in this module.

Covers Acceptance Criteria AC1-AC8 (AC3, AC7, AC8 are not pytest-testable --
see the module-level notes at their section headers below):

- AC1: a full ``segfacet run`` on a fixture containing label values 25/26/29
  produces a JSON report naming them ``L6``/``S1``/``S2`` end-to-end (not
  just at the ``labels.py`` unit level covered by item 093).
- AC2: re-confirms (by direct call, not new machinery) that
  ``bundled_production_reference()`` still loads with its renamed ``"L6"``
  level present and scores an unchanged label-25 record -- item 093's
  AC5/AC7 logic re-invoked as part of this item's full-suite run.
- AC3: CI-observed only (both ``test-numpy-majors`` legs green on the merged
  tree) -- no local pytest test is fabricated for it; see Validation in the
  item spec.
- AC4: a committed-in-code (not committed-binary) synthetic TPTBox-labeled
  fixture, built fresh in every test run, round-trips through the full
  Stage-17 pipeline (``segfacet run``) unconditionally, in every CI
  invocation.
- AC5/AC6: ``real_spineps_fixture_dir()``/``requires_spineps``, modelled
  byte-for-byte on ``tests/test_091_stage14_acceptance.py``'s
  ``real_verse_cohort_dir()``/``requires_verse`` (see
  ``tests/test_091_stage14_acceptance.py:115-128`` and its
  ``test_ac12_requires_verse_marker_is_a_genuine_skipif`` meta-test). AC5 is
  the genuine-skipif meta-test; AC6 is the gated positive test, which SKIPS
  on this fixture-absent host -- that is the correct, expected outcome, not
  a failure.
- AC7/AC8: ``progress.md`` edits / stage-status flips -- not pytest-testable,
  handled directly as documentation edits by the builder/validator.

Adversarial / edge cases (per the item's Testing Strategy):
- ``SEGFACET_SPINEPS_FIXTURE`` set to an existing but empty directory (no
  label maps inside) -- behaves as "no usable fixture found", skips cleanly
  rather than erroring on an empty glob.
- ``SEGFACET_SPINEPS_FIXTURE`` set to a path that exists but is a file, not
  a directory -- treated as absent, not a crash.
- The synthetic TPTBox-labeled fixture includes a label value outside 1-33
  (an unrelated artifact label) -- resolves to ``UNKNOWN``/``is_known() ==
  False`` end-to-end, not a crash.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import List, Optional

import numpy as np
import pytest

from segfacet.cli import main
from segfacet.io import load_volume
from segfacet.labels import UNKNOWN, LabelConvention
from segfacet.reference import ALL_STRATUM, bundled_production_reference, compute_reference_delta

from synthetic import make_labelmap, make_scan, write_nifti


def _run(args: "List[str]", capsys) -> "tuple[int, str, str]":
    """Invoke ``main(args)`` and return ``(exit_code, stdout, stderr)`` --
    the same helper shape used by ``tests/test_cli_run.py``/``test_035_cli_e2e.py``."""
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# =========================================================================== #
# AC1: end-to-end label-convention confirmation via a full `segfacet run`.
# =========================================================================== #


def _write_25_26_29_case(tmp_path):
    """A real synthetic NIfTI pair with three non-touching blocks labelled
    25 (L6), 26 (S1), and 29 (S2) -- the item 093 renamed sacral/coccygeal
    range, exercised through the full pipeline rather than at the
    ``labels.py`` unit level."""
    shape = (24, 24, 24)
    blocks = {
        25: ((1, 6), (1, 6), (1, 6)),
        26: ((9, 14), (9, 14), (9, 14)),
        29: ((17, 22), (17, 22), (17, 22)),
    }
    seg_img = make_labelmap(shape=shape, blocks=blocks, spacing=(1.0, 1.0, 1.0))
    scan_img = make_scan(shape=shape, spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    return scan_path, seg_path


def test_ac1_full_run_json_report_names_l6_s1_s2(tmp_path, capsys):
    """A full ``segfacet run`` on labels 25/26/29 reports L6/S1/S2 -- not the
    legacy S/Cocygis/L6 -- in the JSON report's per-label naming."""
    scan_path, seg_path = _write_25_26_29_case(tmp_path)
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code in (0, 1), f"segfacet run crashed; stderr: {stderr!r}"
    data = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    per_label = data["features"]["per_label"]
    assert per_label["25"]["level_name"] == "L6"
    assert per_label["26"]["level_name"] == "S1"
    assert per_label["29"]["level_name"] == "S2"
    # The legacy names must not appear anywhere in the naming.
    reported_names = {entry["level_name"] for entry in per_label.values()}
    assert "S" not in reported_names
    assert "Cocygis" not in reported_names


def test_ac1_full_run_human_report_text_names_l6_s1_s2(tmp_path, capsys):
    """The plain-text human report (not just the JSON) also names the
    renamed levels correctly -- the item spec calls out 'and the human
    report text' explicitly."""
    scan_path, seg_path = _write_25_26_29_case(tmp_path)
    out_dir = tmp_path / "out"
    _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    text = (out_dir / "segfacet_report.txt").read_text(encoding="utf-8")
    assert "L6" in text
    assert "S1" in text
    assert "S2" in text
    assert "Cocygis" not in text


def test_ac1_stdout_inventory_names_l6_s1_s2(tmp_path, capsys):
    """The CLI's printed label-inventory line (item 004/035 wiring) also
    reflects the renamed convention end-to-end."""
    scan_path, seg_path = _write_25_26_29_case(tmp_path)
    out_dir = tmp_path / "out"
    _, stdout, _ = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert "L6" in stdout
    assert "S1" in stdout
    assert "S2" in stdout


# =========================================================================== #
# AC2: reference_verse_v1.json loads and scores unchanged (re-confirms item
# 093's AC5/AC7 as a checklist item, not new machinery).
# =========================================================================== #


def test_ac2_bundled_production_reference_still_loads_with_l6_level():
    dist = bundled_production_reference()
    assert "S" not in dist.levels
    assert dist.levels["L6"][ALL_STRATUM].level_name == "L6"


def test_ac2_label_25_scores_against_renamed_l6_level_unchanged():
    """A label-25 record (now named L6 per item 093) still resolves against
    the reference's renamed level -- the same join item 093's AC7 exercised,
    re-confirmed here as part of Stage 17's end-to-end close-out."""
    conv = LabelConvention.default()
    reference = bundled_production_reference()
    block = {
        "per_label": {
            "25": {
                "label": 25,
                "level_name": conv.name_of(25),
                "geometry": {"physical_volume_mm3": 60000.0},
            },
        },
    }
    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[25]
    assert label_delta.level_name == "L6"
    assert label_delta.available is True


# =========================================================================== #
# AC3: numpy-major CI matrix. CI-observed only -- no local pytest test.
#
# Both `test-numpy-majors` legs (numpy==1.26.4, numpy==2.0.2) passing on the
# merged tree is a fact about the actual CI run on this item's branch/PR, not
# something a unit test running under a single local interpreter/numpy can
# assert. Per the item's Validation section, the validator confirms this by
# reading the CI run directly.
# =========================================================================== #


# =========================================================================== #
# AC4: a committed-in-code synthetic TPTBox-labeled fixture round-trips
# correctly, unconditionally (no environment gate).
# =========================================================================== #


def build_stage17_synthetic_fixture(tmp_path):
    """Build (in-test, no committed binary) a label map spanning a
    representative set of TPTBox-standard values -- including at least one
    renamed sacral/coccygeal value (25 = L6, 26 = S1) -- plus one value
    outside the recognised 1-33 range (999, an unrelated artifact label) to
    exercise the UNKNOWN path unconditionally. Returns ``(scan_path,
    seg_path)`` under ``tmp_path``."""
    shape = (32, 32, 32)
    blocks = {
        20: ((1, 5), (1, 5), (1, 5)),      # L1
        24: ((7, 11), (7, 11), (7, 11)),   # L5
        25: ((13, 17), (13, 17), (13, 17)),  # L6 (renamed)
        26: ((19, 23), (19, 23), (19, 23)),  # S1 (new)
        999: ((25, 29), (25, 29), (25, 29)),  # unrelated artifact label
    }
    seg_img = make_labelmap(shape=shape, blocks=blocks, spacing=(1.0, 1.0, 1.0))
    scan_img = make_scan(shape=shape, spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    return scan_path, seg_path


def test_ac4_synthetic_fixture_round_trips_with_correct_level_names(tmp_path, capsys):
    scan_path, seg_path = build_stage17_synthetic_fixture(tmp_path)
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code in (0, 1), f"segfacet run crashed; stderr: {stderr!r}"
    data = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    per_label = data["features"]["per_label"]
    assert per_label["20"]["level_name"] == "L1"
    assert per_label["24"]["level_name"] == "L5"
    assert per_label["25"]["level_name"] == "L6"
    assert per_label["26"]["level_name"] == "S1"


def test_ac4_synthetic_fixture_out_of_range_label_resolves_unknown_not_crash(tmp_path, capsys):
    """Adversarial: label 999 (outside 1-33) resolves to UNKNOWN end-to-end
    -- AC1/AC4 do not accidentally depend on every label being recognised."""
    scan_path, seg_path = build_stage17_synthetic_fixture(tmp_path)
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--no-reference"],
        capsys,
    )
    assert code in (0, 1), f"segfacet run crashed; stderr: {stderr!r}"
    assert "Traceback" not in stderr
    data = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    per_label = data["features"]["per_label"]
    assert per_label["999"]["level_name"] == UNKNOWN


# =========================================================================== #
# AC5/AC6: env-gated real-SPINEPS check, modelled on test_091's
# real_verse_cohort_dir()/requires_verse pattern
# (tests/test_091_stage14_acceptance.py:115-128).
# =========================================================================== #


#: Labels for which item 093 changed or introduced the TPTBox-convention
#: name -- a real SPINEPS output containing any of these is a non-trivial
#: check of AC6, not merely "does not crash."
_RENAMED_OR_NEW_NAMES = {25: "L6", 26: "S1", 28: "T13", 29: "S2"}


def real_spineps_fixture_dir() -> "Optional[pathlib.Path]":
    """The real-SPINEPS fixture root from ``SEGFACET_SPINEPS_FIXTURE`` iff
    set AND a directory, else ``None`` -- mirrors
    ``real_verse_cohort_dir``'s contract exactly (item 091)."""
    raw = os.environ.get("SEGFACET_SPINEPS_FIXTURE")
    if not raw:
        return None
    candidate = pathlib.Path(raw)
    return candidate if candidate.is_dir() else None


def _spineps_label_maps(directory: "pathlib.Path") -> "List[pathlib.Path]":
    """NIfTI files directly under ``directory`` -- an empty result (e.g. an
    existing-but-empty directory) means "no usable fixture found", handled
    as absent rather than as an error on an empty glob."""
    return sorted(directory.glob("*.nii.gz")) + sorted(directory.glob("*.nii"))


_spineps_dir = real_spineps_fixture_dir()
_spineps_label_map_paths = _spineps_label_maps(_spineps_dir) if _spineps_dir is not None else []

requires_spineps = pytest.mark.skipif(
    not _spineps_label_map_paths,
    reason=(
        "no real SPINEPS-output fixture found (set SEGFACET_SPINEPS_FIXTURE "
        "to a directory containing at least one .nii/.nii.gz label map)"
    ),
)


def test_ac5_requires_spineps_marker_is_a_genuine_skipif():
    """The marker's condition actually evaluates True on this
    fixture-absent host -- proves AC6 below genuinely SKIPS rather than
    silently passing/erroring (mirrors item 091's
    test_ac12_requires_verse_marker_is_a_genuine_skipif)."""
    assert requires_spineps.mark.name == "skipif"
    condition = requires_spineps.mark.args[0]
    assert isinstance(condition, bool)
    assert condition is True


@requires_spineps
def test_ac6_real_spineps_fixture_level_names_correct():
    """Positive counterpart: on a host with SEGFACET_SPINEPS_FIXTURE pointing
    at a real directory, every present label in every label map resolves to
    a plausible (non-UNKNOWN) TPTBox-convention name, and any of 25/26/28/29
    present resolve to the specific correct renamed name. Skips cleanly
    everywhere else (proven structurally above)."""
    conv = LabelConvention.default()
    directory = real_spineps_fixture_dir()
    assert directory is not None
    label_maps = _spineps_label_maps(directory)
    assert label_maps, "requires_spineps should have skipped for an empty fixture dir"

    any_present = False
    for map_path in label_maps:
        volume = load_volume(map_path, integer_labels=True)
        present_labels = sorted(int(v) for v in np.unique(volume.data) if v != 0)
        for label in present_labels:
            name = conv.name_of(label)
            assert name != UNKNOWN, (
                f"label {label} in {map_path} resolved to UNKNOWN -- expected a "
                f"plausible TPTBox-convention vertebra name"
            )
            if label in _RENAMED_OR_NEW_NAMES:
                any_present = True
                assert name == _RENAMED_OR_NEW_NAMES[label], (
                    f"label {label} in {map_path} resolved to {name!r}, expected "
                    f"{_RENAMED_OR_NEW_NAMES[label]!r}"
                )
    assert any_present, (
        "real SPINEPS fixture contained none of 25/26/28/29 -- AC6 requires "
        "the renamed-name assertion to be exercised, not merely 'no crash'"
    )


# --------------------------------------------------------------------------- #
# Adversarial / edge cases for the real-SPINEPS gate (Testing Strategy).
# --------------------------------------------------------------------------- #


def test_adv_spineps_fixture_dir_unset_returns_none(monkeypatch):
    monkeypatch.delenv("SEGFACET_SPINEPS_FIXTURE", raising=False)
    assert real_spineps_fixture_dir() is None


def test_adv_spineps_fixture_dir_nonexistent_path_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("SEGFACET_SPINEPS_FIXTURE", str(tmp_path / "does-not-exist"))
    assert real_spineps_fixture_dir() is None


def test_adv_spineps_fixture_dir_existing_but_empty_yields_no_label_maps(tmp_path):
    """An existing but empty directory is a valid directory (not None), but
    yields zero usable label maps -- the skip must come from the empty glob,
    not from a crash iterating it."""
    assert real_spineps_fixture_dir.__module__  # sanity: importable
    empty_dir = tmp_path / "empty_fixture"
    empty_dir.mkdir()
    assert empty_dir.is_dir()
    assert _spineps_label_maps(empty_dir) == []


def test_adv_spineps_fixture_dir_path_is_a_file_treated_as_absent(monkeypatch, tmp_path):
    """A path that exists but is a file, not a directory, must be treated as
    absent -- not raise when later globbed."""
    file_path = tmp_path / "not_a_directory.txt"
    file_path.write_text("i am a file")
    monkeypatch.setenv("SEGFACET_SPINEPS_FIXTURE", str(file_path))
    assert real_spineps_fixture_dir() is None


# =========================================================================== #
# AC7/AC8: progress.md edits and stage-status flips are documentation, not
# pytest-testable -- handled directly by the builder/validator, no test here.
# =========================================================================== #
