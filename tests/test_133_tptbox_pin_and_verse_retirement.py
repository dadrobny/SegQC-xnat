"""Tests for item 133 -- tptbox >= 0.7.6 (licence-metadata fix, D9) and the
retirement of ``scripts/refresh_reference.py --verse-cohort`` (D10).

Neither deliverable touches ``src/segfacet/`` -- this is packaging metadata
plus one project tool under ``scripts/``.

Covers Acceptance Criteria AC1-AC13:

- AC1/AC2/AC4: the tptbox pin moves to the exact literal ``tptbox==0.7.6``
  in both ``pyproject.toml`` and ``constraints.txt`` (parsed with
  ``tomllib`` and the same pin-line regex ``test_094`` uses -- never
  regex-on-the-whole-file), the rest of ``constraints.txt``'s pin map is
  byte-for-byte the pre-item map, and the installed distribution's version
  agrees with both pins and parses as >= 0.7.6.
- AC3: the installed ``tptbox`` distribution's ``License`` metadata field,
  read via ``importlib.metadata`` (never a ``pip show`` subprocess), no
  longer declares AGPL/Affero.
- AC5: ``docs/tptbox-install-numpy1.md`` names only the pinned version and
  the correct wheel digest.
- AC6: no file under ``tests/`` still contains the literal
  ``tptbox==0.7.5``.
- AC7: ``test_093``/``test_094`` carry no skip guard keyed on tptbox.
- AC8/AC9: ``--verse-cohort`` (and ``--verse-seg-suffix``) is rejected
  outright -- exit code 2, a single-line stderr pointer naming
  ``scripts/rebuild_verse_reference.py``, no traceback, no
  ``refresh_summary.json`` and no artifact written.
- AC10/AC13: a no-flag run's summary carries exactly the three synthetic
  step names, in order, all ``ran``, and never a ``verse-build``/
  ``verse-evaluate`` step.
- AC11: ``run_refresh`` accepts no ``verse_cohort``/``verse_seg_suffix``
  parameter and its summary carries no ``verse_cohort`` key.
- AC12: the module docstring names ``rebuild_verse_reference.py`` and
  carries no ``--verse-cohort`` usage example.

Until the builder lands the bump + retirement, AC1-AC4, AC6, AC8-AC12 read
red against the pre-item source and the still-installed 0.7.5 wheel --
expected; AC3/AC4 are written against ``importlib.metadata`` precisely so
they go green the moment the new wheel is installed, with no re-authoring.

Adversarial / edge cases:
- ``--verse-cohort`` pointing at a nonexistent path -- still exit 2 with the
  pointer, not the old "skipped, path does not exist" outcome.
- ``--verse-cohort ""`` (empty string) -- treated as supplied, not a silent
  success.
- ``--verse-cohort`` with a trailing slash.
- ``--verse-seg-suffix`` supplied without ``--verse-cohort``.
- ``--out`` under a not-yet-existing nested parent, combined with the
  retired flag -- still exit 2 and the parent is not created.
- Two no-flag runs into different ``--out`` directories produce equal step
  name/status pairs (item 083 AC11's determinism property, preserved).
- Version-comparison edge: versions are parsed as tuples of ints, so a
  future ``0.7.10`` correctly compares >= ``0.7.6`` (a string comparison
  would not).
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import inspect
import io
import json
import re
import sys
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import nibabel as nib
import pytest

from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.intensity import paint_clean_scan

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"
INSTALL_DOC_PATH = REPO_ROOT / "docs" / "tptbox-install-numpy1.md"
TESTS_DIR = REPO_ROOT / "tests"
REFRESH_MODULE_PATH = REPO_ROOT / "scripts" / "refresh_reference.py"
REBUILD_MODULE_PATH = REPO_ROOT / "scripts" / "rebuild_verse_reference.py"

EXPECTED_TPTBOX_VERSION = "0.7.6"
EXPECTED_WHEEL_SHA256 = "16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4"

#: constraints.txt's complete pin map (name -> version, lower-cased/hyphenated
#: the same way ``_constraints_pins`` normalises), minus tptbox, recorded
#: from the pre-item file so a drive-by lockfile regeneration is caught
#: (AC2).
_PRE_ITEM_OTHER_CONSTRAINTS_PINS = {
    "numpy": "2.4.6",
    "scipy": "1.17.1",
    "scikit-image": "0.26.0",
    "nibabel": "5.4.2",
    "pyyaml": "6.0.3",
    "jsonschema": "4.26.0",
    "attrs": "26.1.0",
    "certifi": "2026.7.22",
    "charset-normalizer": "3.4.9",
    "connected-components-3d": "3.29.0",
    "contourpy": "1.3.3",
    "cycler": "0.12.1",
    "dill": "0.3.9",
    "fastremap": "1.20.0",
    "fill-voids": "2.1.2",
    "fonttools": "4.63.0",
    "idna": "3.18",
    "imageio": "2.37.4",
    "importlib-resources": "7.1.0",
    "joblib": "1.5.3",
    "jsonschema-specifications": "2025.9.1",
    "kiwisolver": "1.5.0",
    "lazy-loader": "0.5",
    "matplotlib": "3.11.1",
    "narwhals": "2.24.0",
    "networkx": "3.6.1",
    "packaging": "26.2",
    "pillow": "12.3.0",
    "pynrrd": "1.1.3",
    "pyparsing": "3.3.2",
    "python-dateutil": "2.9.0.post0",
    "referencing": "0.37.0",
    "requests": "2.34.2",
    "rpds-py": "2026.6.3",
    "scikit-learn": "1.9.0",
    "simpleitk": "2.5.5",
    "six": "1.17.0",
    "threadpoolctl": "3.6.0",
    "tifffile": "2026.3.3",
    "tqdm": "4.69.1",
    "typing-extensions": "4.16.0",
    "urllib3": "2.7.0",
}

#: Pins deliberately ADDED to constraints.txt after item 133, each named here
#: with the change that added it. AC2's guarantee is "no pin item 133 did not
#: intend to touch moves", not "the file never grows again": every pre-item
#: pin above must still hold at its recorded version, and any pin that is
#: neither recorded above nor listed here still fails the comparison.
_POST_ITEM_ADDED_CONSTRAINTS_PINS = {
    # The CI test runner. Every `python -m pytest` step in ci.yml runs `-n 4`
    # as of 2026-09-01 (branch ci/xdist-and-pip-cache), and the `test` job
    # installs `-e .[dev] -c constraints.txt`, so the runner is pinned with
    # the rest. Not part of the Docker image's runtime graph -- a constraint
    # pins a version, it never pulls a package in.
    "pytest-xdist": "3.8.0",
}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


def _read_constraints() -> str:
    return CONSTRAINTS_PATH.read_text(encoding="utf-8")


def _constraints_pins() -> dict:
    """Mirrors ``test_094_tptbox_image_layer.py``'s ``_constraints_pins`` --
    one pin-line regex per line, never regex-on-the-whole-file."""
    pins = {}
    for raw_line in _read_constraints().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s]+)$", line)
        if not match:
            continue
        name = match.group(1).lower().replace("_", "-")
        version = match.group(2)
        pins[name] = version
    return pins


def _pyproject_tptbox_specs() -> list:
    dependencies = _load_pyproject()["project"]["dependencies"]
    return [dep for dep in dependencies if dep.lower().startswith("tptbox")]


def _version_tuple(version: str):
    return tuple(int(part) for part in version.split("."))


def _load_refresh_module():
    spec = importlib.util.spec_from_file_location("refresh_reference_133", REFRESH_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_rebuild_module():
    spec = importlib.util.spec_from_file_location(
        "rebuild_verse_reference_133", REBUILD_MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _capture_main(rr, argv):
    """Run main(argv), capturing stdout/stderr separately; return
    (rc, stdout_text, stderr_text)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = rr.main(argv)
    return rc, out_buf.getvalue(), err_buf.getvalue()


def _no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def _read_summary(out: Path) -> dict:
    return json.loads((out / "refresh_summary.json").read_text(encoding="utf-8"))


def _build_nested_verse_cohort(dest_dir: Path, rvr) -> Path:
    """Write a tiny 2-subject cohort in the **real** nested VerSe19 layout
    (``docs/aide/dataset-verse19.md``) -- ``derivatives/sub-verseNNN/`` for
    the mask, ``rawdata/sub-verseNNN/`` for the CT -- using the suffix
    constants owned by ``scripts/rebuild_verse_reference.py`` (item 123),
    not any constant from ``refresh_reference.py`` (which no longer owns
    the real-VerSe convention after this item)."""
    for i in range(2):
        subject_id = f"sub-verse{i:03d}"
        derivatives_dir = dest_dir / "derivatives" / subject_id
        rawdata_dir = dest_dir / "rawdata" / subject_id
        derivatives_dir.mkdir(parents=True, exist_ok=True)
        rawdata_dir.mkdir(parents=True, exist_ok=True)

        spine = build_clean_spine(
            levels=("L1", "L2", "L3", "L4", "L5"),
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        scan_img = paint_clean_scan(spine.seg_img, seed=0)
        nib.save(spine.seg_img, str(derivatives_dir / f"{subject_id}{rvr.VERSE_SEG_SUFFIX}"))
        nib.save(scan_img, str(rawdata_dir / f"{subject_id}{rvr.VERSE_CT_SUFFIX}"))
    return dest_dir


# =========================================================================== #
# AC1/AC4: pyproject.toml's tptbox pin moves to 0.7.6, exact
# =========================================================================== #


def test_ac1_tptbox_pin_is_exactly_0_7_6():
    tptbox_specs = _pyproject_tptbox_specs()
    assert tptbox_specs == ["tptbox==0.7.6"]


# =========================================================================== #
# AC2: constraints.txt's pin moves with it; nothing else in it moves
# =========================================================================== #


def test_ac2_constraints_tptbox_pin_moved():
    pins = _constraints_pins()
    assert pins.get("tptbox") == "0.7.6"


def test_ac2_constraints_other_pins_unchanged():
    pins = _constraints_pins()
    other_pins = {name: version for name, version in pins.items() if name != "tptbox"}
    assert other_pins == {
        **_PRE_ITEM_OTHER_CONSTRAINTS_PINS,
        **_POST_ITEM_ADDED_CONSTRAINTS_PINS,
    }


# =========================================================================== #
# AC3: the installed distribution's License field is no longer AGPL
# =========================================================================== #


def test_ac3_installed_license_field_not_agpl_or_affero():
    license_field = importlib.metadata.metadata("tptbox")["License"]
    assert license_field is not None and license_field.strip(), "License field is empty"
    lowered = license_field.lower()
    assert "agpl" not in lowered, f"observed License field: {license_field!r}"
    assert "affero" not in lowered, f"observed License field: {license_field!r}"


# =========================================================================== #
# AC4: the environment and both pin files agree, and parse as >= 0.7.6
# =========================================================================== #


def test_ac4_installed_version_matches_both_pins():
    installed_version = importlib.metadata.version("tptbox")
    tptbox_specs = _pyproject_tptbox_specs()
    assert len(tptbox_specs) == 1
    pyproject_version = tptbox_specs[0].split("==", 1)[1]
    constraints_version = _constraints_pins().get("tptbox")
    assert installed_version == pyproject_version == constraints_version


def test_ac4_installed_version_parses_at_least_0_7_6():
    installed_version = importlib.metadata.version("tptbox")
    assert _version_tuple(installed_version) >= _version_tuple(EXPECTED_TPTBOX_VERSION)


# =========================================================================== #
# AC5: the install document names only the pinned version + digest
# =========================================================================== #


def test_ac5_install_doc_names_only_pinned_version():
    text = INSTALL_DOC_PATH.read_text(encoding="utf-8")
    tptbox_specs = _pyproject_tptbox_specs()
    pyproject_version = tptbox_specs[0].split("==", 1)[1]
    found_versions = set(re.findall(r"tptbox==([0-9][0-9a-zA-Z.\-]*)", text))
    assert found_versions == {pyproject_version}


def test_ac5_install_doc_names_expected_wheel_digest():
    text = INSTALL_DOC_PATH.read_text(encoding="utf-8")
    assert EXPECTED_WHEEL_SHA256 in text


# =========================================================================== #
# AC6: no stale version literal survives in the suite
# =========================================================================== #


def test_ac6_no_stale_pin_literal_anywhere_under_tests():
    # The needle itself must still be the exact stale-pin string this AC
    # guards against -- built at runtime so this module (which discusses the
    # retired pin in its own docstring/messages) carries no matching literal
    # for its own sweep to trip over.
    stale_pin = "tptbox==" + "0.7.5"
    assert stale_pin == "tptbox==0.7.5"
    offending = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in TESTS_DIR.rglob("*.py")
        if path.name != Path(__file__).name and stale_pin in path.read_text(encoding="utf-8")
    )
    assert offending == [], f"stale tptbox==0.7.5 literal(s) in: {offending}"


# =========================================================================== #
# AC7: the tptbox consumers cannot skip
# =========================================================================== #


@pytest.mark.parametrize(
    "module_name", ["test_093_tptbox_label_convention.py", "test_094_tptbox_image_layer.py"]
)
def test_ac7_no_skip_guard_keyed_on_tptbox(module_name):
    text = (TESTS_DIR / module_name).read_text(encoding="utf-8")
    assert re.search(r"importorskip\([^)]*tptbox", text, re.IGNORECASE) is None
    assert re.search(r"skipif\([^)]*tptbox", text, re.IGNORECASE) is None


# =========================================================================== #
# AC8/AC9: the retired mode fails loudly with a pointer and does no work
# =========================================================================== #


def test_ac8_verse_cohort_flag_rejected_with_pointer(tmp_path):
    rr = _load_refresh_module()
    rvr = _load_rebuild_module()
    verse_dir = _build_nested_verse_cohort(tmp_path / "verse-cohort", rvr)
    out = tmp_path / "out"

    rc, stdout_text, stderr_text = _capture_main(
        rr, ["--out", str(out), "--verse-cohort", str(verse_dir)]
    )

    assert rc == 2
    combined = stdout_text + stderr_text
    assert _no_traceback(combined)
    stderr_lines = [line for line in stderr_text.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, f"expected a single-line stderr message, got: {stderr_text!r}"
    assert "rebuild_verse_reference.py" in stderr_lines[0]


def test_ac9_refused_run_writes_no_summary_and_no_artifact(tmp_path):
    rr = _load_refresh_module()
    rvr = _load_rebuild_module()
    verse_dir = _build_nested_verse_cohort(tmp_path / "verse-cohort", rvr)
    out = tmp_path / "out"

    rc, _, _ = _capture_main(rr, ["--out", str(out), "--verse-cohort", str(verse_dir)])

    assert rc == 2
    assert not (out / "refresh_summary.json").exists()
    if out.exists():
        assert list(out.iterdir()) == []


# =========================================================================== #
# AC10/AC13: the summary no longer carries VerSe steps
# =========================================================================== #


def test_ac10_summary_steps_are_exactly_the_three_synthetic_ones_in_order(tmp_path):
    rr = _load_refresh_module()
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])

    assert rc == 0
    summary = _read_summary(out)
    step_names = [step["name"] for step in summary["steps"]]
    assert step_names == [
        "synthetic-default-rebuild",
        "synthetic-eval-cohort",
        "synthetic-evaluate",
    ]


def test_ac10_no_verse_step_names_appear():
    rr = _load_refresh_module()
    source = REFRESH_MODULE_PATH.read_text(encoding="utf-8")
    # A step name literal, not merely a symbol reference: neither retired
    # step name string should still be produced anywhere in the module.
    assert '"verse-build"' not in source
    assert '"verse-evaluate"' not in source


def test_ac13_synthetic_path_still_runs_all_three_steps(tmp_path):
    rr = _load_refresh_module()
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])

    assert rc == 0
    assert (out / "refresh_summary.json").is_file()
    summary = _read_summary(out)
    assert len(summary["steps"]) == 3
    for step in summary["steps"]:
        assert step["status"] == "ran"


# =========================================================================== #
# AC11: the API stops advertising the mode
# =========================================================================== #


def test_ac11_run_refresh_signature_drops_verse_parameters():
    rr = _load_refresh_module()
    params = inspect.signature(rr.run_refresh).parameters
    assert "verse_cohort" not in params
    assert "verse_seg_suffix" not in params


def test_ac11_returned_summary_has_no_verse_cohort_key(tmp_path):
    rr = _load_refresh_module()
    summary = rr.run_refresh(tmp_path / "out")
    assert "verse_cohort" not in summary


# =========================================================================== #
# AC12: the docstring stops advertising the mode
# =========================================================================== #


def test_ac12_docstring_names_rebuild_script_and_drops_verse_cohort_usage():
    source = REFRESH_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree)
    assert docstring is not None
    assert "rebuild_verse_reference.py" in docstring
    assert "--verse-cohort" not in docstring


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_nonexistent_verse_cohort_rejected_not_skipped(tmp_path):
    rr = _load_refresh_module()
    nonexistent = tmp_path / "no-such-verse-dir"
    out = tmp_path / "out"

    rc, _, stderr_text = _capture_main(
        rr, ["--out", str(out), "--verse-cohort", str(nonexistent)]
    )

    assert rc == 2
    assert "rebuild_verse_reference.py" in stderr_text
    assert not (out / "refresh_summary.json").exists()


def test_adversarial_empty_string_verse_cohort_is_treated_as_supplied(tmp_path):
    rr = _load_refresh_module()
    out = tmp_path / "out"

    rc, _, stderr_text = _capture_main(rr, ["--out", str(out), "--verse-cohort", ""])

    assert rc == 2
    assert "rebuild_verse_reference.py" in stderr_text


def test_adversarial_verse_cohort_trailing_slash_still_rejected(tmp_path):
    rr = _load_refresh_module()
    rvr = _load_rebuild_module()
    verse_dir = _build_nested_verse_cohort(tmp_path / "verse-cohort", rvr)
    out = tmp_path / "out"

    rc, _, stderr_text = _capture_main(
        rr, ["--out", str(out), "--verse-cohort", str(verse_dir) + "/"]
    )

    assert rc == 2
    assert "rebuild_verse_reference.py" in stderr_text


def test_adversarial_verse_seg_suffix_alone_still_rejected(tmp_path):
    rr = _load_refresh_module()
    out = tmp_path / "out"

    rc, _, stderr_text = _capture_main(
        rr, ["--out", str(out), "--verse-seg-suffix", "_seg-vert_msk.nii.gz"]
    )

    assert rc == 2
    assert "rebuild_verse_reference.py" in stderr_text


def test_adversarial_out_parent_not_created_when_retired_flag_supplied(tmp_path):
    rr = _load_refresh_module()
    out = tmp_path / "brand_new_parent" / "nested" / "out"
    assert not out.parent.exists()

    rc, _, _ = _capture_main(rr, ["--out", str(out), "--verse-cohort", str(tmp_path / "x")])

    assert rc == 2
    assert not out.parent.exists()
    assert not out.exists()


def test_adversarial_two_no_flag_runs_produce_equal_step_pairs(tmp_path):
    rr = _load_refresh_module()
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    rr.main(["--out", str(out_a)])
    rr.main(["--out", str(out_b)])

    pairs_a = [(step["name"], step["status"]) for step in _read_summary(out_a)["steps"]]
    pairs_b = [(step["name"], step["status"]) for step in _read_summary(out_b)["steps"]]
    assert pairs_a  # non-empty: a run that wrote no steps would trivially "match"
    assert pairs_a == pairs_b


def test_adversarial_version_tuple_parsing_orders_correctly_unlike_strings():
    assert _version_tuple("0.7.10") > _version_tuple("0.7.6")
    # The whole point of AC4's tuple comparison: naive string comparison
    # gets this backwards.
    assert "0.7.10" < "0.7.6"
