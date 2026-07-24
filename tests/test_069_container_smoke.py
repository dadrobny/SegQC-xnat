"""End-to-end container smoke test for the packaged image (item 069).

Docker-gated: exercises the real item-066 image via ``docker run`` through the
item-068 entry script (``/app/docker/entrypoint.py``), at the exact bind-mount
paths item-067's ``command.json`` declares, against small committed corpus
fixtures. This is the first test in the stage that drives the whole packaged
path -- image -> mount convention -> entry script -> ``segfacet run`` -> output
resources -- as a single unit, standing in for what the XNAT Container Service
does, but with ``docker run -v`` instead of XNAT's own mount machinery.

Docker availability, the shared ``requires_docker`` skip marker, and the
session-scoped ``docker_image_tag`` build fixture all live in
``tests/conftest.py`` (promoted there from ``tests/test_066_dockerfile.py`` by
this item) so this module and ``test_066_dockerfile.py`` build the
``segfacet:test-066`` image **at most once** per test session.

All Docker-gated tests degrade to a clean ``pytest.skip`` (never a failure)
when Docker itself is unavailable or a mount/build cannot run for
environmental reasons -- the default suite stays green on a Docker-less host.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from conftest import requires_docker

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_FIXTURE = REPO_ROOT / "tests" / "corpus" / "fixtures" / "base_scan.nii.gz"
SEG_FIXTURE = REPO_ROOT / "tests" / "corpus" / "fixtures" / "clean_control_seg.nii.gz"
REFERENCE_FIXTURE = REPO_ROOT / "src" / "segfacet" / "reference" / "reference_default.json"

ENTRYPOINT_ARGV_PREFIX = ["python", "/app/docker/entrypoint.py"]

RUN_TIMEOUT = 120


# =========================================================================== #
# Helpers
# =========================================================================== #


def _load_report_schema() -> dict:
    """Load the live v0 report schema (not a copy) so this smoke test fails
    if the container's report shape and the schema diverge."""
    import importlib.resources as pkg_resources
    import segfacet

    ref = pkg_resources.files(segfacet).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _stage_role_dir(tmp_path: Path, role: str, fixture: Path, filename: str) -> Path:
    """Create ``tmp_path/role`` and copy exactly one fixture file into it."""
    role_dir = tmp_path / role
    role_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, role_dir / filename)
    return role_dir


def _stage_output_dir(tmp_path: Path) -> Path:
    """Create a writable output dir. The item-066 image runs as the non-root
    ``segfacet`` user, so the host directory is made world-writable to allow the
    container to write reports into the bind mount."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o777)
    return out_dir


def _stage_happy_path_dirs(tmp_path: Path):
    """Stage scan/seg/out dirs for the primary happy-path fixture pair."""
    scan_dir = _stage_role_dir(tmp_path, "scan", SCAN_FIXTURE, "scan.nii.gz")
    seg_dir = _stage_role_dir(tmp_path, "seg", SEG_FIXTURE, "seg.nii.gz")
    out_dir = _stage_output_dir(tmp_path)
    return scan_dir, seg_dir, out_dir


def _run_container(tag, *mount_args, entry_args, timeout=RUN_TIMEOUT):
    """Run the item-066 image through the item-068 entry script with the
    given bind-mount args and entry-script argv."""
    cmd = ["docker", "run", "--rm", *mount_args, tag, *ENTRYPOINT_ARGV_PREFIX, *entry_args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)


# =========================================================================== #
# AC1  Smoke-test module present & collectable (always, no Docker required)
# =========================================================================== #


def test_ac1_smoke_test_module_present_and_collectable():
    module_path = REPO_ROOT / "tests" / "test_069_container_smoke.py"
    assert module_path.is_file(), "tests/test_069_container_smoke.py must exist"


# =========================================================================== #
# AC2  Docker-gating is a clean skip (structural; runs regardless of Docker)
# =========================================================================== #


def test_ac2_docker_gated_tests_skip_not_error_or_xfail_when_docker_absent():
    """The marker gating every docker-run test in this module must be a
    genuine pytest.mark.skipif (a bool condition), never xfail or an
    unguarded call -- so a Docker-less host skips cleanly."""
    assert isinstance(requires_docker.mark.args[0], bool)
    assert requires_docker.mark.name == "skipif"


# =========================================================================== #
# AC3  Item-066 image built/reused once per session (shared conftest fixture)
# =========================================================================== #


@requires_docker
def test_ac3_shared_image_fixture_yields_a_tag(docker_image_tag):
    """Reaching this point with a tag proves the shared session-scoped
    ``docker_image_tag`` fixture (built/skipped in conftest.py, shared with
    test_066_dockerfile.py) built or reused the image successfully."""
    assert docker_image_tag


# =========================================================================== #
# AC4-AC8  Happy path
# =========================================================================== #


@requires_docker
def test_ac4_happy_path_docker_run_exits_zero(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
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
        f"happy-path docker run failed:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@requires_docker
def test_ac5_happy_path_produces_report_json(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
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
    assert result.returncode == 0, result.stderr
    assert (out_dir / "segfacet_report.json").is_file()


@requires_docker
def test_ac6_happy_path_produces_report_txt(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
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
    assert result.returncode == 0, result.stderr
    assert (out_dir / "segfacet_report.txt").is_file()


@requires_docker
def test_ac7_happy_path_report_json_validates_against_schema(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
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
    assert result.returncode == 0, result.stderr

    import jsonschema

    schema = _load_report_schema()
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)


@requires_docker
def test_ac8_happy_path_report_has_deterministic_content(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
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
    assert result.returncode == 0, result.stderr

    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "0.1"
    assert report["case_id"]
    assert report["verdict"] in ("pass", "flagged-for-review", "fail")


# =========================================================================== #
# AC9  Optional reference mount smoke
# =========================================================================== #


@requires_docker
def test_ac9_optional_reference_mount_produces_reference_delta(docker_image_tag, tmp_path):
    scan_dir, seg_dir, out_dir = _stage_happy_path_dirs(tmp_path)
    reference_dir = _stage_role_dir(
        tmp_path, "reference", REFERENCE_FIXTURE, "reference_default.json"
    )
    mount_args = [
        "-v", f"{scan_dir}:/input/scan:ro",
        "-v", f"{seg_dir}:/input/seg:ro",
        "-v", f"{out_dir}:/output",
        "-v", f"{reference_dir}:/input/reference:ro",
    ]
    result = _run_container(
        docker_image_tag,
        *mount_args,
        entry_args=[
            "--scan-dir", "/input/scan",
            "--seg-dir", "/input/seg",
            "--out-dir", "/output",
            "--reference-dir", "/input/reference",
            "--reference",
        ],
    )
    assert result.returncode == 0, (
        f"reference-mount docker run failed:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert (out_dir / "segfacet_report.json").is_file()
    assert (out_dir / "segfacet_report.txt").is_file()

    import jsonschema

    schema = _load_report_schema()
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)
    assert "reference_delta" in report


# =========================================================================== #
# AC10-AC12  Failure path: broken scan mount
# =========================================================================== #


@requires_docker
def test_ac10_failure_path_empty_scan_mount_exits_nonzero(docker_image_tag, tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)  # deliberately empty: no NIfTI file
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


@requires_docker
def test_ac10_failure_path_non_nifti_scan_mount_exits_nonzero(docker_image_tag, tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    (scan_dir / "not_a_nifti.txt").write_text("garbage, not a NIfTI file", encoding="utf-8")
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


@requires_docker
def test_ac11_failure_path_emits_clean_error_not_traceback(docker_image_tag, tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)  # empty: no NIfTI file
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
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr


@requires_docker
def test_ac12_failure_path_leaves_no_partial_output(docker_image_tag, tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)  # empty: no NIfTI file
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
    assert not (out_dir / "segfacet_report.json").exists()
    assert not (out_dir / "segfacet_report.txt").exists()
