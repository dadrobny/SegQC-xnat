"""Tests for scoping ``test-numpy-majors`` off environment-gated modules
(item 113).

Covers AC1-AC7. This is a **workflow-parsing** test module -- it never
executes CI, it parses the committed ``.github/workflows/ci.yml`` (via
PyYAML, a core project dependency -- see ``pyproject.toml``'s
``dependencies`` list) and, for AC7 only, shells out to a local
``pytest --collect-only`` subprocess twice (unscoped vs. the job's own
scoped expression, parsed out of the workflow rather than duplicated as a
literal here).

Design notes (see the item spec's Testing Strategy and Assumptions):

- AC1/AC2 assert the ``test-numpy-majors`` Test step's command actually
  excludes the three Docker-gated modules (whole-module ``--ignore``) and
  the PyRadiomics-gated test class (``--deselect``, narrower than a whole
  module -- the rest of ``test_features_radiomics.py`` is numpy-sensitive
  builtin-backend coverage that must stay collected, per AC3).
- AC3 is a non-regression check: representative numpy-sensitive modules
  from each package area, plus ``test_features_radiomics.py`` as a whole
  module, must not be excluded.
- AC4 checks the *raw* text (comments are not part of the parsed YAML
  structure) surrounding the job for the required explanation.
- AC5/AC6 pin the ``test`` and ``verify-environment-gated`` jobs' step
  commands to their exact current form, normalized for incidental
  whitespace only -- so a change to *those* jobs (which this item must not
  touch) fails loudly.
- AC7 is the drift-proof heart of this module: collect the full suite's
  node IDs once, collect again with the job's real scoped expression
  (parsed out of ci.yml), and assert the set difference equals *exactly*
  the gated node IDs -- not a hardcoded count, which would rot on every
  unrelated test added elsewhere in the repo. This single module-scoped
  fixture pays the ~12s subprocess cost once and every AC7 test reuses it.

Until the builder lands the scoping change, ``test-numpy-majors`` runs
``python -m pytest`` unscoped, so AC1/AC2/AC4/AC7's core-removal test are
*expected to fail* -- that is the correct pre-implementation state.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

DOCKER_GATED_MODULES = (
    "tests/test_066_dockerfile.py",
    "tests/test_069_container_smoke.py",
    "tests/test_070_acceptance_stage9.py",
)
PYRADIOMICS_GATED_TARGET = "tests/test_features_radiomics.py::TestPresentPath"

# One representative numpy-sensitive module per package area named in AC3
# (features, heuristics, eval, synth, reference, pipeline).
REPRESENTATIVE_NUMPY_MODULES = (
    "tests/test_016_features_json.py",
    "tests/test_heuristics_bounds_source.py",
    "tests/test_053_eval_harness.py",
    "tests/test_040_synthetic_corpus.py",
    "tests/test_043_reference_aggregation.py",
    "tests/test_010_pipeline.py",
)

# AC5/AC6 pinned expected forms (normalized -- see _normalize_run). The
# `-n 4` in the two pytest invocations is pytest-xdist, added to every CI
# pytest step on 2026-09-01 to cut the workflow's wall clock (windows-latest
# was the critical path at 21.0 min); it changes how the same selection is
# scheduled, never what is selected, so AC5/AC6 keep pinning the commands and
# AC7 keeps comparing the same collected node IDs.
EXPECTED_TEST_INSTALL_RUN = "pip install -e .[dev] -c constraints.txt"
EXPECTED_TEST_TEST_RUN = "python -m pytest -n 4"
EXPECTED_TEST_MATRIX_OS = ["ubuntu-latest", "windows-latest"]
EXPECTED_VG_INSTALL_BASE_RUN = "pip install -e .[dev]"
EXPECTED_VG_INSTALL_VERSIONEER_RUN = "pip install versioneer"
EXPECTED_VG_INSTALL_PYRADIOMICS_RUN = 'pip install --no-build-isolation "pyradiomics>=3.0"'
EXPECTED_VG_DOCKER_VERSION_RUN = "docker version"
EXPECTED_VG_RUN_GATED_RUN = (
    "python -m pytest -n 4 -v --junitxml=gated-results.xml "
    "tests/test_features_radiomics.py "
    "tests/test_066_dockerfile.py "
    "tests/test_069_container_smoke.py "
    "tests/test_070_acceptance_stage9.py"
)
EXPECTED_VG_ASSERT_NO_SKIPS_RUN = (
    'python .github/scripts/assert_no_skips.py gated-results.xml '
    '--allow "PyRadiomics happens to be installed"'
)

# Non-triviality floor for AC7 (see module docstring: not an exact count).
MIN_SCOPED_COLLECTED = 4000


# =========================================================================== #
# Parsing helpers
# =========================================================================== #


def _normalize_run(cmd: str) -> str:
    """Collapse a (possibly multi-line, backslash-continued) shell command
    into single-spaced tokens, so incidental YAML block-scalar formatting
    never trips a comparison."""
    cmd = cmd.replace("\\\n", " ")
    return " ".join(cmd.split())


def _step_run(job: dict, step_name: str) -> str:
    for step in job.get("steps", []):
        if step.get("name") == step_name:
            run = step.get("run")
            assert run is not None, f"step {step_name!r} has no 'run:' command"
            return run
    raise AssertionError(f"no step named {step_name!r} found in job {job!r}")


def _extract_flag_values(cmd: str, flag: str) -> list[str]:
    """Return every value passed to ``flag`` (``--ignore``/``--deselect``),
    accepting both ``--flag=value`` and ``--flag value`` spacing."""
    normalized = _normalize_run(cmd)
    pattern = re.compile(rf"{re.escape(flag)}(?:=|\s+)(\S+)")
    return pattern.findall(normalized)


def _extra_pytest_args(run_cmd: str) -> list[str]:
    """Strip the ``python -m pytest`` prefix off the Test step's command and
    return the remaining arguments, tokenized -- these are appended to a
    local ``--collect-only`` invocation for AC7.

    ``-n``/``--numprocesses`` is dropped: it selects how many xdist workers
    execute the run, never which node IDs are collected, and AC7's two
    ``--collect-only`` subprocesses must differ *only* in the job's
    selection expression. Leaving it in would also make the scoped
    collection listing come back from workers while the baseline came from
    the controller -- a difference in the comparison that has nothing to do
    with what this module is testing.
    """
    normalized = _normalize_run(run_cmd)
    match = re.match(r"^python3?\s+-m\s+pytest\b(.*)$", normalized)
    assert match, (
        "test-numpy-majors Test step is expected to be a 'python -m pytest "
        f"...' invocation; got {run_cmd!r}"
    )
    args = shlex.split(match.group(1))
    kept: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-n", "--numprocesses"):
            skip_next = True
            continue
        if arg.startswith("-n") or arg.startswith("--numprocesses="):
            continue
        kept.append(arg)
    return kept


def _job_comment_and_body(ci_text: str, job_name: str) -> str:
    """Return the raw text of ``job_name``'s own body plus any contiguous
    comment block immediately preceding it (comments are stripped by YAML
    parsing, so AC4 must read the raw source)."""
    lines = ci_text.splitlines()
    job_line_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    job_indices: dict[str, int] = {}
    for i, line in enumerate(lines):
        m = job_line_re.match(line)
        if m:
            job_indices[m.group(1)] = i
    assert job_name in job_indices, f"job {job_name!r} not found in {CI_YML_PATH}"
    start = job_indices[job_name]

    comment_start = start
    i = start - 1
    while i >= 0 and (lines[i].strip() == "" or lines[i].strip().startswith("#")):
        comment_start = i
        i -= 1

    following = sorted(v for v in job_indices.values() if v > start)
    end = following[0] if following else len(lines)
    return "\n".join(lines[comment_start:end])


def _is_gated_node_id(node_id: str) -> bool:
    for module in DOCKER_GATED_MODULES:
        if node_id == module or node_id.startswith(f"{module}::"):
            return True
    return node_id == PYRADIOMICS_GATED_TARGET or node_id.startswith(
        f"{PYRADIOMICS_GATED_TARGET}::"
    )


def _collect_node_ids(extra_args: list[str]) -> set[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    node_ids: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        # Node IDs are exactly "tests/....py::...", one per line. Anchoring
        # on the "tests/" prefix (rather than merely "contains '::'")
        # excludes summary/warning lines that happen to embed a node-id-like
        # substring (e.g. a wrapped parametrize-collection warning).
        if line.startswith("tests/") and "::" in line:
            node_ids.add(line)
    assert node_ids, (
        f"--collect-only with args {extra_args!r} collected nothing; "
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    return node_ids


# =========================================================================== #
# Fixtures
# =========================================================================== #


@pytest.fixture(scope="module")
def ci_workflow():
    text = CI_YML_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    jobs = parsed["jobs"]
    numpy_job = jobs["test-numpy-majors"]
    test_job = jobs["test"]
    gated_job = jobs["verify-environment-gated"]
    return {
        "text": text,
        "numpy_majors_run": _step_run(numpy_job, "Test"),
        "numpy_majors_comment_block": _job_comment_and_body(text, "test-numpy-majors"),
        "test_install_run": _step_run(test_job, "Install"),
        "test_test_run": _step_run(test_job, "Test"),
        "test_matrix_os": test_job["strategy"]["matrix"]["os"],
        "vg_install_base_run": _step_run(
            gated_job, "Install base project (numpy etc. first)"
        ),
        "vg_install_versioneer_run": _step_run(
            gated_job, "Install pyradiomics's undeclared build-time dependencies"
        ),
        "vg_install_pyradiomics_run": _step_run(
            gated_job, "Install pyradiomics without build isolation"
        ),
        "vg_docker_version_run": _step_run(gated_job, "Confirm docker is available"),
        "vg_run_gated_run": _step_run(gated_job, "Run environment-gated test modules"),
        "vg_assert_no_skips_run": _step_run(
            gated_job, "Fail if any environment-gated test was skipped"
        ),
    }


@pytest.fixture(scope="module")
def collect_only_sets(ci_workflow):
    """Module-scoped: pays the two ``--collect-only`` subprocess runs (~12s
    combined) exactly once for every AC7 test in this module."""
    extra_args = _extra_pytest_args(ci_workflow["numpy_majors_run"])
    baseline = _collect_node_ids([])
    scoped = _collect_node_ids(extra_args)
    return baseline, scoped


# =========================================================================== #
# AC1: the Docker modules are deselected
# =========================================================================== #


@pytest.mark.parametrize("module", DOCKER_GATED_MODULES)
def test_ac1_docker_module_is_ignored(ci_workflow, module):
    ignored = _extract_flag_values(ci_workflow["numpy_majors_run"], "--ignore")
    assert module in ignored, (
        f"{module} must be passed to --ignore in test-numpy-majors' Test step "
        f"(current command: {ci_workflow['numpy_majors_run']!r})"
    )


# =========================================================================== #
# AC2: the PyRadiomics-gated tests are deselected
# =========================================================================== #


def test_ac2_pyradiomics_present_path_class_is_deselected(ci_workflow):
    deselected = _extract_flag_values(ci_workflow["numpy_majors_run"], "--deselect")
    assert PYRADIOMICS_GATED_TARGET in deselected, (
        f"{PYRADIOMICS_GATED_TARGET} must be passed to --deselect in "
        f"test-numpy-majors' Test step (current command: "
        f"{ci_workflow['numpy_majors_run']!r})"
    )


# =========================================================================== #
# AC3: numpy-sensitive coverage is retained
# =========================================================================== #


@pytest.mark.parametrize("module", REPRESENTATIVE_NUMPY_MODULES)
def test_ac3_representative_numpy_sensitive_module_is_not_excluded(ci_workflow, module):
    ignored = _extract_flag_values(ci_workflow["numpy_majors_run"], "--ignore")
    deselected = _extract_flag_values(ci_workflow["numpy_majors_run"], "--deselect")
    assert module not in ignored, f"{module} must not be --ignore'd (AC3)"
    assert not any(d.startswith(module) for d in deselected), (
        f"{module} must not have any test --deselect'd (AC3)"
    )


def test_ac3_radiomics_module_is_not_wholly_ignored(ci_workflow):
    # AC2 deselects only the PyRadiomics-present-path class; the rest of
    # test_features_radiomics.py (the builtin-backend coverage) is
    # numpy-sensitive and must remain collectible, so the module itself
    # must never appear behind a whole-module --ignore.
    ignored = _extract_flag_values(ci_workflow["numpy_majors_run"], "--ignore")
    assert "tests/test_features_radiomics.py" not in ignored


# =========================================================================== #
# AC4: the intent is legible in the workflow
# =========================================================================== #


def test_ac4_job_comment_names_verify_environment_gated(ci_workflow):
    block = ci_workflow["numpy_majors_comment_block"]
    assert "verify-environment-gated" in block, (
        "the test-numpy-majors job (or its preceding comment block) must "
        "name verify-environment-gated as the owner of environment-gated "
        "verification"
    )


def test_ac4_job_comment_states_numpy_agnosticism_purpose(ci_workflow):
    block = ci_workflow["numpy_majors_comment_block"].lower()
    assert "numpy" in block and ("major" in block or "agnostic" in block), (
        "the job's comment must state that it proves numpy-major agnosticism"
    )


# =========================================================================== #
# AC5: verify-environment-gated is untouched
# =========================================================================== #


def test_ac5_verify_environment_gated_install_steps_unchanged(ci_workflow):
    assert (
        _normalize_run(ci_workflow["vg_install_base_run"]) == EXPECTED_VG_INSTALL_BASE_RUN
    )
    assert (
        _normalize_run(ci_workflow["vg_install_versioneer_run"])
        == EXPECTED_VG_INSTALL_VERSIONEER_RUN
    )
    assert (
        _normalize_run(ci_workflow["vg_install_pyradiomics_run"])
        == EXPECTED_VG_INSTALL_PYRADIOMICS_RUN
    )
    assert (
        _normalize_run(ci_workflow["vg_docker_version_run"]) == EXPECTED_VG_DOCKER_VERSION_RUN
    )


def test_ac5_verify_environment_gated_run_command_unchanged(ci_workflow):
    assert _normalize_run(ci_workflow["vg_run_gated_run"]) == EXPECTED_VG_RUN_GATED_RUN


def test_ac5_verify_environment_gated_assert_no_skips_command_unchanged(ci_workflow):
    assert (
        _normalize_run(ci_workflow["vg_assert_no_skips_run"]) == EXPECTED_VG_ASSERT_NO_SKIPS_RUN
    )


# =========================================================================== #
# AC6: the main test job is untouched
# =========================================================================== #


def test_ac6_test_job_install_and_test_commands_unchanged(ci_workflow):
    assert _normalize_run(ci_workflow["test_install_run"]) == EXPECTED_TEST_INSTALL_RUN
    assert _normalize_run(ci_workflow["test_test_run"]) == EXPECTED_TEST_TEST_RUN


def test_ac6_test_job_matrix_still_covers_both_platforms(ci_workflow):
    assert ci_workflow["test_matrix_os"] == EXPECTED_TEST_MATRIX_OS


# =========================================================================== #
# AC7: the selection is verifiable locally / cannot silently drift
# =========================================================================== #


def test_ac7_scoped_collection_removes_exactly_the_gated_node_ids(collect_only_sets):
    baseline, scoped = collect_only_sets
    gated_in_baseline = {nid for nid in baseline if _is_gated_node_id(nid)}
    assert gated_in_baseline, (
        "sanity check failed: none of the declared gated targets were "
        "collectible in the unscoped run -- the target list itself is stale"
    )
    removed = baseline - scoped
    missing_from_removal = gated_in_baseline - removed
    unexpectedly_removed = removed - gated_in_baseline
    assert removed == gated_in_baseline, (
        "the scoped test-numpy-majors expression must remove exactly the "
        f"gated node ids. Not removed (under-deselection): "
        f"{sorted(missing_from_removal)}. Removed but not gated "
        f"(over-deselection): {sorted(unexpectedly_removed)}"
    )


def test_ac7_scoped_collection_is_non_trivial(collect_only_sets):
    _, scoped = collect_only_sets
    assert len(scoped) > MIN_SCOPED_COLLECTED, (
        f"scoped collection only found {len(scoped)} tests; expected more "
        f"than {MIN_SCOPED_COLLECTED} -- the exclusion expression looks far "
        "too broad"
    )


def test_ac7_scoped_collection_is_a_strict_subset_of_baseline(collect_only_sets):
    baseline, scoped = collect_only_sets
    assert scoped <= baseline
    assert scoped < baseline, "scoping must actually remove something"


# =========================================================================== #
# Adversarial: renamed gated module, empty exclusion set, malformed workflow
# =========================================================================== #


def test_adv_empty_exclusion_expression_yields_no_ignores_or_deselects():
    assert _extract_flag_values("python -m pytest", "--ignore") == []
    assert _extract_flag_values("python -m pytest", "--deselect") == []


def test_adv_renamed_docker_module_does_not_silently_satisfy_ac1():
    # If tests/test_066_dockerfile.py were renamed and the workflow's
    # exclusion expression updated to the new name without this module's
    # constant list being updated, this proves the mismatch is caught
    # (exact string matching, not a fuzzy/substring match).
    synthetic_cmd = "python -m pytest --ignore=tests/test_066_dockerfile_v2.py"
    ignored = _extract_flag_values(synthetic_cmd, "--ignore")
    assert "tests/test_066_dockerfile.py" not in ignored
    assert "tests/test_066_dockerfile_v2.py" in ignored


def test_adv_malformed_workflow_file_raises_on_parse(tmp_path):
    malformed = tmp_path / "ci.yml"
    malformed.write_bytes(b"jobs:\n  test-numpy-majors:\n  - not: [valid, yaml\n")
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(malformed.read_text(encoding="utf-8"))


def test_adv_missing_job_key_raises_assertion(ci_workflow):
    with pytest.raises(AssertionError):
        _job_comment_and_body(ci_workflow["text"], "job-that-does-not-exist")
