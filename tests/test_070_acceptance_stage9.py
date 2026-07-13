"""Stage-9 acceptance suite (item 070): closes Stage 9.

This module is the Stage-9 closer. It writes NO new production code -- every
executable Stage-9 artifact (items 066-069) is already merged. It ties those
artifacts into one coherent, testable path and proves the roadmap's literal
Stage-9 acceptance bar holds, decomposed into its three clauses:

  AC8  clause 1 -- container produces JSON + human report (Docker-gated,
       reuses item 069's ``requires_docker`` marker / ``docker_image_tag``
       fixture and bind-mount contract from ``tests/conftest.py``).
  AC9  clause 2 -- ``command.json`` validates (no Docker; mirrors item 067's
       structural checks in ``tests/test_067_command_json.py``).
  AC10 clause 3 -- install steps documented (no Docker; roll-up over
       ``docs/deployment.md``, distinct from the individual-topic checks in
       ``tests/test_070_deployment_docs.py``).

AC7 (this module exists and is collect-clean) and AC11 (the literal roadmap
sentence is traceable in this closer) are structural/self-referential and
require no Docker either.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import requires_docker

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = Path(__file__).resolve()
COMMAND_JSON_PATH = REPO_ROOT / "command.json"
DEPLOYMENT_DOC_PATH = REPO_ROOT / "docs" / "deployment.md"

SCAN_FIXTURE = REPO_ROOT / "tests" / "corpus" / "fixtures" / "base_scan.nii.gz"
SEG_FIXTURE = REPO_ROOT / "tests" / "corpus" / "fixtures" / "clean_control_seg.nii.gz"

ENTRYPOINT_ARGV_PREFIX = ["python", "/app/docker/entrypoint.py"]
RUN_TIMEOUT = 120

REQUIRED_TOP_LEVEL_KEYS = (
    "name",
    "image",
    "type",
    "command-line",
    "mounts",
    "inputs",
    "outputs",
)

# Matches a mount-path-shaped token (``/input/<segment>`` or ``/output``) as a
# whole path component, mirroring item 067's closure-check regex.
MOUNT_PATH_TOKEN_RE = re.compile(r"/input/[A-Za-z0-9_-]+|/output(?![A-Za-z0-9_-])")

# The roadmap's literal Stage-9 acceptance sentence (roadmap.md, Stage 9 ->
# "Validation / acceptance", verbatim minus the trailing "(G5)" objective
# tag). AC11 requires this exact sentence be traceable in this closer module.
STAGE9_ACCEPTANCE_SENTENCE = "Container runs the pipeline on a mounted case, producing JSON + human report; `command.json` validates; install steps documented"


# =========================================================================== #
# Helpers
# =========================================================================== #


def _load_command_json() -> dict:
    return json.loads(COMMAND_JSON_PATH.read_text(encoding="utf-8"))


def _normalize_path(path: str) -> str:
    if not path:
        return path
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _mounts_by_path(command: dict) -> dict:
    result = {}
    for mount in command.get("mounts", []):
        path = mount.get("path")
        if path is not None:
            result[_normalize_path(path)] = mount
    return result


def _mount_path_tokens_in_command_line(command_line: str) -> set:
    return set(MOUNT_PATH_TOKEN_RE.findall(command_line))


def _mount_closure_undeclared(command: dict) -> set:
    """Return the set of mount-path tokens referenced in ``command-line`` that
    are NOT declared in ``mounts`` -- an empty set means the command-line's
    mount references are fully closed over declared mounts."""
    tokens = _mount_path_tokens_in_command_line(command.get("command-line", ""))
    declared_paths = set(_mounts_by_path(command).keys())
    return tokens - declared_paths


def _stage_role_dir(tmp_path: Path, role: str, fixture: Path, filename: str) -> Path:
    import shutil

    role_dir = tmp_path / role
    role_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, role_dir / filename)
    return role_dir


def _stage_output_dir(tmp_path: Path) -> Path:
    import os

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o777)
    return out_dir


def _run_container(tag, *mount_args, entry_args, timeout=RUN_TIMEOUT):
    import subprocess

    cmd = ["docker", "run", "--rm", *mount_args, tag, *ENTRYPOINT_ARGV_PREFIX, *entry_args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)


@pytest.fixture(scope="module")
def command() -> dict:
    return _load_command_json()


# =========================================================================== #
# AC7  Stage-9 acceptance module present & collectable
# =========================================================================== #


def test_ac7_acceptance_module_present_and_collectable():
    """This assertion itself requires no Docker: merely reaching it proves the
    module imported and collected cleanly under pytest."""
    module_path = REPO_ROOT / "tests" / "test_070_acceptance_stage9.py"
    assert module_path.is_file(), "tests/test_070_acceptance_stage9.py must exist"


# =========================================================================== #
# AC8  clause 1 -- container produces JSON + human report (Docker-gated)
# =========================================================================== #


@requires_docker
def test_ac8_container_run_exits_zero_and_produces_both_reports(docker_image_tag, tmp_path):
    scan_dir = _stage_role_dir(tmp_path, "scan", SCAN_FIXTURE, "scan.nii.gz")
    seg_dir = _stage_role_dir(tmp_path, "seg", SEG_FIXTURE, "seg.nii.gz")
    out_dir = _stage_output_dir(tmp_path)
    mount_args = [
        "-v", f"{scan_dir}:/input/scan:ro",
        "-v", f"{seg_dir}:/input/seg:ro",
        "-v", f"{out_dir}:/output",
    ]
    result = _run_container(
        docker_image_tag,
        *mount_args,
        entry_args=[
            "--scan-dir", "/input/scan",
            "--seg-dir", "/input/seg",
            "--out-dir", "/output",
        ],
    )
    assert result.returncode == 0, (
        f"Stage-9 acceptance run failed:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert (out_dir / "segqc_report.json").is_file(), "no JSON report produced"
    assert (out_dir / "segqc_report.txt").is_file(), "no human report produced"

    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    schema_ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(schema_ref.read_text(encoding="utf-8"))
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)


@requires_docker
def test_ac8_failure_path_empty_scan_mount_exits_nonzero_with_no_partial_report(
    docker_image_tag, tmp_path
):
    """Adversarial: an empty scan mount must exit non-zero and leave no
    partial report in the output mount -- a thin echo of item 069's AC12,
    guarding the "no partial output" contract the deployment docs promise."""
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)  # deliberately empty: no NIfTI
    seg_dir = _stage_role_dir(tmp_path, "seg", SEG_FIXTURE, "seg.nii.gz")
    out_dir = _stage_output_dir(tmp_path)
    mount_args = [
        "-v", f"{scan_dir}:/input/scan:ro",
        "-v", f"{seg_dir}:/input/seg:ro",
        "-v", f"{out_dir}:/output",
    ]
    result = _run_container(
        docker_image_tag,
        *mount_args,
        entry_args=[
            "--scan-dir", "/input/scan",
            "--seg-dir", "/input/seg",
            "--out-dir", "/output",
        ],
    )
    assert result.returncode != 0
    assert not (out_dir / "segqc_report.json").exists()
    assert not (out_dir / "segqc_report.txt").exists()


# =========================================================================== #
# AC9  clause 2 -- command.json validates (no Docker)
# =========================================================================== #


def test_ac9_command_json_is_valid_json_object():
    command = _load_command_json()
    assert isinstance(command, dict)


@pytest.mark.parametrize("key", REQUIRED_TOP_LEVEL_KEYS)
def test_ac9_command_json_required_top_level_key_present(command, key):
    assert key in command, f"required top-level key {key!r} is missing from command.json"


def test_ac9_command_json_mount_closure_holds(command):
    """Every mount path referenced in command-line must be a declared
    mounts[*].path -- the internal-consistency clause of AC9."""
    undeclared = _mount_closure_undeclared(command)
    assert not undeclared, (
        f"command.json's command-line references undeclared mount path(s): {undeclared}"
    )


def test_ac9_negative_closure_check_rejects_synthetic_broken_command_json():
    """Adversarial: proves the mount-closure check is not vacuously passing
    by running it against a synthetic command.json-shaped dict that declares
    a mount referenced in command-line but never declared in ``mounts``."""
    broken_command = {
        "command-line": (
            "python /app/docker/entrypoint.py --scan-dir /input/scan "
            "--extra-dir /input/extra --out-dir /output"
        ),
        "mounts": [
            {"name": "scan-in", "path": "/input/scan"},
            {"name": "reports-out", "path": "/output"},
        ],
    }
    undeclared = _mount_closure_undeclared(broken_command)
    assert undeclared == {"/input/extra"}, (
        "closure check must flag the undeclared /input/extra mount reference"
    )


# =========================================================================== #
# AC10  clause 3 -- install steps documented (acceptance roll-up, no Docker)
# =========================================================================== #


def test_ac10_deployment_doc_exists_and_documents_install_workflow():
    """Roll-up: docs/deployment.md exists and documents the full install
    workflow -- build command, command.json install, input configuration --
    distinct from AC2-AC5's individual-topic checks in
    tests/test_070_deployment_docs.py."""
    assert DEPLOYMENT_DOC_PATH.is_file(), "docs/deployment.md must exist"
    text = DEPLOYMENT_DOC_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "docker build" in lowered, "deployment doc must document a build command"
    assert "command.json" in lowered, "deployment doc must document installing command.json"
    assert "xnat" in lowered, "deployment doc must document the XNAT install context"

    # Input-configuration roll-up: scan, segmentation and the mode toggles.
    assert "scan" in lowered
    assert ("segmentation" in lowered) or ("seg" in lowered)
    assert "reference" in lowered
    assert "intensity" in lowered


# =========================================================================== #
# AC11  literal Stage-9 wording traceable in the closer
# =========================================================================== #


def test_ac11_stage9_acceptance_sentence_constant_matches_roadmap_wording():
    """roadmap.md hard-wraps its prose across lines (soft line breaks in
    Markdown), so whitespace is normalised to a single space before the
    substring comparison -- this compares the *logical* sentence, not raw
    bytes, while still catching any real wording drift."""
    roadmap_path = REPO_ROOT / "docs" / "aide" / "roadmap.md"
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    normalized_roadmap_text = re.sub(r"\s+", " ", roadmap_text)
    normalized_sentence = re.sub(r"\s+", " ", STAGE9_ACCEPTANCE_SENTENCE)
    assert normalized_sentence in normalized_roadmap_text, (
        "the module's STAGE9_ACCEPTANCE_SENTENCE constant must match roadmap.md's "
        "literal Stage-9 'Validation / acceptance' wording verbatim"
    )


def test_ac11_stage9_acceptance_sentence_embedded_in_module_source():
    """The acceptance module must record the roadmap's literal Stage-9
    sentence verbatim in its own source (module docstring or a module-level
    constant), so AC8/AC9/AC10 are self-documenting against the roadmap bar."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert STAGE9_ACCEPTANCE_SENTENCE in source, (
        "tests/test_070_acceptance_stage9.py must embed the verbatim roadmap "
        "Stage-9 acceptance sentence"
    )
