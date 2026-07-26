"""Tests for the Python 3.11 / numpy-range environment migration (item 095).

Covers AC1, AC2, and AC4. AC1/AC2 are packaging-metadata assertions: they
parse the committed root ``pyproject.toml`` via ``tomllib`` (stdlib on
Python 3.11+, which this project now requires) and check the
``requires-python`` floor, the classifier list, and the exact ``numpy``
dependency string. AC4 parses the committed root ``constraints.txt`` and
checks that its ``numpy==`` pin satisfies the declared ``>=1.26,<3`` range
and that no TPTBox-transitive package name has leaked in early (TPTBox is
item 094's edit, not this item's).

AC3 (a Python<3.11 install is rejected cleanly by pip) and AC5/AC6/AC7
(CI job shape/behaviour) are, per this item's own Testing Strategy, not
expressible as a single local ``pytest`` run -- AC3 needs an actual Python
3.10 interpreter (not guaranteed to be present on the machine running this
suite) and AC5/AC6/AC7 need a live CI execution. They are documented as
Validation-level checks in the item spec rather than faked here. This module
does, however, statically check that the ``test-numpy-majors`` CI job exists
with the expected matrix and that the existing ``test`` job's install-step
shape is unchanged, since both of those are observable by parsing the
committed ``ci.yml`` without actually running it.

Note on ``constraints.txt``: per this item's own Assumptions, the file is
legitimately regenerated *twice* across items 095/094 -- this item's own
regeneration reflected only the pre-TPTBox six-package core, but item 094
(TPTBox becoming a required core dependency) regenerates it again to add
TPTBox and its transitives. On this repo's current state (item 094 landed),
``constraints.txt`` legitimately contains TPTBox -- so this module no longer
asserts TPTBox's *absence*, only that item 095's own concerns (the numpy
pin/range, the Python floor, the other five original pins) still hold.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# =========================================================================== #
# Helpers
# =========================================================================== #


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


def _read_constraints() -> str:
    return CONSTRAINTS_PATH.read_text(encoding="utf-8")


def _constraints_pins() -> dict:
    """Parse constraints.txt into {normalised_name: version}, tolerating
    comments, blank lines, and environment markers."""
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


def _read_ci_workflow() -> str:
    return CI_WORKFLOW_PATH.read_text(encoding="utf-8")


# =========================================================================== #
# AC1: requires-python raised, stale classifiers removed
# =========================================================================== #


def test_ac1_requires_python_is_311():
    project = _load_pyproject()["project"]
    assert project["requires-python"] == ">=3.11"


def test_ac1_no_stale_python_version_classifiers():
    classifiers = _load_pyproject()["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.9" not in classifiers
    assert "Programming Language :: Python :: 3.10" not in classifiers


def test_ac1_311_and_312_classifiers_retained():
    classifiers = _load_pyproject()["project"]["classifiers"]
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers


# =========================================================================== #
# AC2: numpy dependency is a range, not an unbounded lower bound
# =========================================================================== #


def test_ac2_numpy_dependency_is_the_declared_range():
    dependencies = _load_pyproject()["project"]["dependencies"]
    assert "numpy>=1.26,<3" in dependencies


def test_ac2_no_unbounded_numpy_lower_bound_remains():
    dependencies = _load_pyproject()["project"]["dependencies"]
    numpy_specs = [dep for dep in dependencies if dep.lower().startswith("numpy")]
    assert numpy_specs == ["numpy>=1.26,<3"]


def test_ac2_other_core_dependency_bounds_unchanged():
    # This item touches only the numpy bound -- the other five core
    # dependencies' lower bounds are untouched.
    dependencies = _load_pyproject()["project"]["dependencies"]
    unchanged = {
        "scipy>=1.7",
        "scikit-image>=0.19",
        "nibabel>=4.0",
        "PyYAML>=5.4",
        "jsonschema>=3.2",
    }
    assert unchanged.issubset(set(dependencies))


# =========================================================================== #
# AC4: constraints.txt regenerated for the new floor. This item's own
# regeneration was pre-TPTBox (TPTBox is item 094's later edit, which
# legitimately regenerates the file again to add TPTBox and its
# transitives) -- these checks cover item 095's own concerns only, not
# TPTBox's absence/presence.
# =========================================================================== #


def test_ac4_constraints_numpy_pin_satisfies_declared_range():
    pins = _constraints_pins()
    assert "numpy" in pins
    version = pins["numpy"]
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", version)
    assert match is not None, f"unparseable numpy version pin: {version!r}"
    major = int(match.group(1))
    minor = int(match.group(2))
    # >=1.26,<3
    assert (major, minor) >= (1, 26)
    assert major < 3


def test_ac4_all_six_core_dependencies_still_pinned():
    pins = _constraints_pins()
    for package_name in ("numpy", "scipy", "scikit-image", "nibabel", "pyyaml", "jsonschema"):
        assert package_name in pins, f"{package_name!r} missing from constraints.txt"


# =========================================================================== #
# AC5/AC6: CI workflow shape (static, config-level -- a live CI run is the
# real Validation surface for AC5/AC6/AC7, per this item's Testing Strategy)
# =========================================================================== #


def test_ac6_numpy_majors_job_exists_with_both_measured_legs():
    ci_text = _read_ci_workflow()
    assert "test-numpy-majors" in ci_text
    assert "1.26.4" in ci_text
    assert "2.0.2" in ci_text


def test_ac5_existing_test_job_install_step_unchanged():
    ci_text = _read_ci_workflow()
    # The existing `test` job's constraints-pinned install step is the
    # byte-identity-sensitive one this item must not restructure.
    assert "pip install -e .[dev] -c constraints.txt" in ci_text


def test_ac7_verify_environment_gated_job_unaffected():
    ci_text = _read_ci_workflow()
    assert "verify-environment-gated" in ci_text
    assert "pip install -e .[dev]" in ci_text
    assert "pyradiomics" in ci_text.lower()


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_numpy_range_upper_bound_is_major_3_not_a_narrower_pin():
    # A hypothetical future 2.x release must still satisfy the declared
    # range -- the upper bound is <3, not e.g. <2.1. Confirmed by checking
    # the exact declared string rather than a loosely-matched substring.
    dependencies = _load_pyproject()["project"]["dependencies"]
    numpy_spec = next(dep for dep in dependencies if dep.lower().startswith("numpy"))
    assert numpy_spec.endswith("<3")
    assert "<3." not in numpy_spec  # not e.g. "<3.0" narrowed further than major 3


def test_adv_constraints_numpy_pin_is_exact_not_a_range():
    # constraints.txt pins with `==`, not a range -- a `>=`/`~=` pin here
    # would mean the lockfile recipe was not followed.
    constraints_text = _read_constraints()
    numpy_lines = [
        line
        for line in constraints_text.splitlines()
        if line.strip().lower().startswith("numpy==")
    ]
    assert len(numpy_lines) == 1


def test_adv_constraints_header_comment_describes_declared_core_dependencies():
    # The header comment must describe the declared core dependencies it was
    # filtered down to. At item 095's own landing this read "six declared
    # core dependencies" (pre-TPTBox); item 094 legitimately regenerated the
    # file again to add TPTBox as a seventh core dependency, updating the
    # count in the same header comment -- so this checks the description
    # exists and mentions all six of item 095's own core packages by name,
    # rather than pinning the exact (now superseded) count string.
    constraints_text = _read_constraints()
    assert "declared core" in constraints_text
    assert "dependencies" in constraints_text
    for package_name in ("numpy", "scipy", "scikit-image", "nibabel", "PyYAML", "jsonschema"):
        assert package_name in constraints_text


def test_adv_pyproject_is_still_valid_toml():
    # Malformed-input guard: if a hand-edit broke the TOML syntax while
    # bumping requires-python/numpy, tomllib.load raises loudly here rather
    # than any downstream test failing confusingly.
    project = _load_pyproject()
    assert "project" in project
    assert "dependencies" in project["project"]
