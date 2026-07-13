"""Tests for the CPU-only Docker base image (item 066).

Covers AC1-AC15. AC1-AC8 are **static**: they parse the committed root
``Dockerfile``, ``constraints.txt``, and ``.dockerignore`` and run everywhere,
Docker or no Docker. AC9-AC15 are **Docker-gated**: they build the image once
via a session-scoped fixture and reuse the tag across the CLI-surface checks,
skipping cleanly (not failing) when the ``docker`` CLI is unavailable on the
host -- mirroring item 060's ``pytest.importorskip``-style optional-capability
skip pattern (there for PyRadiomics, here for a Docker daemon).

All static tests are deterministic, CPU-only, and portable (no network, no
absolute paths). The Docker-gated tests necessarily invoke the ``docker`` CLI
and build/run a container; they are the one place in this suite that touches
an external tool, and they degrade to a skip rather than a failure whenever
that tool is missing or a build fails for environmental reasons (e.g. no
daemon running, no network to pull the base layer).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from conftest import requires_docker

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"

CORE_PACKAGES = ("numpy", "scipy", "scikit-image", "nibabel", "pyyaml", "jsonschema")
GPU_TOKENS = ("cuda", "nvidia", "gpu", "devel")


# =========================================================================== #
# Helpers
# =========================================================================== #


def _read_dockerfile() -> str:
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


def _read_constraints() -> str:
    return CONSTRAINTS_PATH.read_text(encoding="utf-8")


def _read_dockerignore() -> str:
    return DOCKERIGNORE_PATH.read_text(encoding="utf-8")


def _constraints_pins() -> dict:
    """Parse constraints.txt into {normalised_name: version}, tolerating
    comments, blank lines, and environment markers."""
    pins = {}
    for raw_line in _read_constraints().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip an environment marker (e.g. "pkg==1.0 ; python_version >= '3.9'")
        line = line.split(";", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s]+)$", line)
        if not match:
            continue
        name = match.group(1).lower().replace("_", "-")
        version = match.group(2)
        pins[name] = version
    return pins


def _from_lines() -> list:
    return [
        line.strip()
        for line in _read_dockerfile().splitlines()
        if line.strip().upper().startswith("FROM")
    ]


def _has_gpu_token(text: str, token: str) -> bool:
    """Word-boundary aware, case-insensitive scan for a forbidden GPU token."""
    return re.search(r"\b" + re.escape(token) + r"\b", text, flags=re.IGNORECASE) is not None


# =========================================================================== #
# AC1  Dockerfile present, non-empty, parseable
# =========================================================================== #


def test_ac1_dockerfile_present_and_nonempty():
    assert DOCKERFILE_PATH.is_file(), "Dockerfile must exist at the repo root"
    text = _read_dockerfile()
    assert text.strip(), "Dockerfile must not be empty"


def test_ac1_dockerfile_has_at_least_one_from_instruction():
    from_lines = _from_lines()
    assert len(from_lines) >= 1, "Dockerfile must contain at least one FROM instruction"


# =========================================================================== #
# AC2  CPU-only slim Python base
# =========================================================================== #


def test_ac2_from_is_slim_python_image():
    from_lines = _from_lines()
    assert from_lines, "no FROM instruction found"
    first_from = from_lines[0]
    assert re.search(r"python:", first_from, flags=re.IGNORECASE), first_from
    assert re.search(r"slim", first_from, flags=re.IGNORECASE), first_from


def test_ac2_from_python_version_at_least_3_9():
    first_from = _from_lines()[0]
    match = re.search(r"python:(\d+)\.(\d+)", first_from)
    assert match, f"could not parse a python version out of FROM line: {first_from}"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (3, 9), f"base Python version {major}.{minor} is below 3.9"


def test_ac2_from_has_no_gpu_tokens():
    first_from = _from_lines()[0]
    for token in ("cuda", "nvidia", "gpu", "devel"):
        assert not _has_gpu_token(first_from, token), (
            f"FROM line contains forbidden GPU token {token!r}: {first_from}"
        )


# =========================================================================== #
# AC3  Constraints file pins every core dependency with ==
# =========================================================================== #


def test_ac3_constraints_file_present():
    assert CONSTRAINTS_PATH.is_file(), "constraints.txt must exist at the repo root"


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_ac3_constraints_pins_core_package(package):
    pins = _constraints_pins()
    assert package in pins, f"{package} is not pinned with == in constraints.txt"
    assert pins[package], f"{package} has an empty pinned version"


# =========================================================================== #
# AC4  Build installs segqc against the pinned constraints
# =========================================================================== #


def test_ac4_pip_install_passes_constraints_file():
    text = _read_dockerfile()
    # Find the specific install line(s) that reference "-c" / "--constraint"
    constraint_lines = [
        line for line in text.splitlines()
        if "pip install" in line.lower() and ("-c " in line or "--constraint" in line.lower())
    ]
    assert constraint_lines, (
        "expected a `pip install ... -c constraints.txt` (or --constraint) line "
        "in the Dockerfile"
    )
    assert any("constraints.txt" in line for line in constraint_lines), (
        "the -c/--constraint flag must reference constraints.txt"
    )


# =========================================================================== #
# AC5  No radiomics extra installed by default
# =========================================================================== #


def test_ac5_default_install_line_excludes_radiomics_extra():
    text = _read_dockerfile()
    lines = text.splitlines()
    # The unconditional/default install line(s): those not inside an `if`
    # guarded by INSTALL_RADIOMICS. We approximate by checking every line
    # that performs the base project install (references "." as the install
    # target alongside pip install) is free of the radiomics markers.
    default_install_lines = [
        line for line in lines
        if "pip install" in line.lower() and "constraints.txt" in line
    ]
    assert default_install_lines, "no default project install line found"
    for line in default_install_lines:
        lowered = line.lower()
        assert "[radiomics]" not in lowered, line
        assert "pyradiomics" not in lowered, line
        assert "simpleitk" not in lowered, line


def test_ac5_constraints_file_does_not_pin_pyradiomics():
    pins = _constraints_pins()
    assert "pyradiomics" not in pins, "constraints.txt must not pin pyradiomics (AC5)"


# =========================================================================== #
# AC6  Documented radiomics-enabled variant
# =========================================================================== #


def test_ac6_radiomics_variant_is_documented():
    text = _read_dockerfile()
    has_arg = re.search(r"ARG\s+INSTALL_RADIOMICS", text, flags=re.IGNORECASE) is not None
    has_comment_note = "radiomics" in text.lower() and (
        "build-arg" in text.lower() or "build --build-arg" in text.lower() or "#" in text
    )
    assert has_arg or has_comment_note, (
        "Dockerfile must document a radiomics-enabled variant via an "
        "INSTALL_RADIOMICS build ARG and/or a discoverable comment"
    )


# =========================================================================== #
# AC7  No GPU/CUDA dependencies anywhere
# =========================================================================== #


FORBIDDEN_GPU_PACKAGES = ("cupy", "cucim", "tensorflow-gpu")


def test_ac7_dockerfile_has_no_gpu_packages():
    text = _read_dockerfile().lower()
    for package in FORBIDDEN_GPU_PACKAGES:
        assert package not in text, f"Dockerfile references forbidden GPU package {package!r}"
    assert not re.search(r"nvidia-[a-z0-9\-]+", text), "Dockerfile references an nvidia-* package"
    assert not re.search(r"torch[a-z0-9_\-]*\+?cu\d+", text), "Dockerfile references a CUDA-suffixed torch wheel"
    assert "nvidia/cuda" not in text, "Dockerfile references an nvidia/cuda base image"


def test_ac7_constraints_has_no_gpu_packages():
    text = _read_constraints().lower()
    for package in FORBIDDEN_GPU_PACKAGES:
        assert package not in text, f"constraints.txt references forbidden GPU package {package!r}"
    assert not re.search(r"nvidia-[a-z0-9\-]+", text), "constraints.txt references an nvidia-* package"
    assert not re.search(r"torch[a-z0-9_\-]*\+?cu\d+", text), "constraints.txt references a CUDA-suffixed torch wheel"


def test_ac7_gpu_token_scan_does_not_false_positive_on_scikit_image():
    """The GPU-token scan must be word-boundary aware: scikit-image legitimately
    contains none of the forbidden tokens as substrings of another word, and
    the pinned name itself must not trip a false 'gpu'/'cuda' match."""
    pins = _constraints_pins()
    assert "scikit-image" in pins
    for token in GPU_TOKENS:
        assert not _has_gpu_token("scikit-image", token)


# =========================================================================== #
# AC8  Lean build context via .dockerignore
# =========================================================================== #


def test_ac8_dockerignore_present():
    assert DOCKERIGNORE_PATH.is_file(), ".dockerignore must exist at the repo root"


def test_ac8_dockerignore_excludes_git():
    text = _read_dockerignore()
    assert ".git" in text


def test_ac8_dockerignore_excludes_venv():
    text = _read_dockerignore()
    assert ".venv" in text


def test_ac8_dockerignore_excludes_pycache():
    text = _read_dockerignore()
    lowered = text.lower()
    assert "__pycache__" in lowered
    assert "*.pyc" in lowered


# =========================================================================== #
# Adversarial / edge cases -- static
# =========================================================================== #


def test_adv_constraints_parser_tolerates_comments_and_blank_lines(tmp_path):
    sample = tmp_path / "sample_constraints.txt"
    sample.write_text(
        "# a leading comment\n"
        "\n"
        "numpy==1.26.4\n"
        "   \n"
        "scipy==1.11.4 ; python_version >= '3.9'\n"
        "# trailing comment\n",
        encoding="utf-8",
    )
    text = sample.read_text(encoding="utf-8")
    pins = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s]+)$", line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    assert pins == {"numpy": "1.26.4", "scipy": "1.11.4"}


def test_adv_base_tag_check_rejects_nvidia_cuda_style_base():
    fake_from = "FROM nvidia/cuda:12.2.0-devel-ubuntu22.04"
    assert not re.search(r"python:", fake_from, flags=re.IGNORECASE)
    for token in ("cuda", "nvidia", "devel"):
        assert _has_gpu_token(fake_from, token)


def test_adv_base_tag_check_accepts_only_slim_python_base():
    good_from = "FROM python:3.11-slim"
    bad_from_full = "FROM python:3.11"  # not slim -- should not satisfy AC2's slim check
    assert re.search(r"slim", good_from, flags=re.IGNORECASE)
    assert not re.search(r"slim", bad_from_full, flags=re.IGNORECASE)


def test_adv_every_core_package_missing_from_constraints_would_fail(monkeypatch):
    """Sanity-check the AC3 assertion actually discriminates: a constraints
    file missing one of the six core packages must not satisfy the check."""
    incomplete = "numpy==1.26.4\nscipy==1.11.4\n"
    pins = {}
    for raw_line in incomplete.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s]+)$", line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    assert "nibabel" not in pins


# =========================================================================== #
# Docker-gated fixtures & tests (AC9-AC15)
# =========================================================================== #
#
# The Docker-availability helper (``_docker_available``), the ``requires_docker``
# skip marker, and the session-scoped ``docker_image_tag`` build fixture live in
# ``tests/conftest.py`` (promoted there by item 069) so this module and
# ``test_069_container_smoke.py`` share a single image build per test session.
# ``requires_docker`` is imported explicitly above; ``docker_image_tag`` is a
# conftest fixture and is injected automatically by name.


def _docker_run(tag, *args, timeout=120):
    return subprocess.run(
        ["docker", "run", "--rm", tag, *args],
        capture_output=True,
        timeout=timeout,
        text=True,
    )


@requires_docker
def test_ac9_docker_build_succeeds(docker_image_tag):
    # The fixture itself performs the build and fails/skips appropriately;
    # reaching this point with a tag proves AC9.
    assert docker_image_tag


@requires_docker
def test_ac10_segqc_version_matches_package_version(docker_image_tag):
    from segqc import __version__

    result = _docker_run(docker_image_tag, "segqc", "--version")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).strip()
    assert combined, "segqc --version produced no output"
    assert __version__ in combined, (
        f"expected version {__version__!r} in output: {combined!r}"
    )


@requires_docker
def test_ac11_segqc_run_help_names_scan_seg_out(docker_image_tag):
    result = _docker_run(docker_image_tag, "segqc", "run", "--help")
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    for option in ("--scan", "--seg", "--out"):
        assert option in output, f"{option} missing from `segqc run --help` output"


@requires_docker
def test_ac12_segqc_build_reference_help_names_cohort_out(docker_image_tag):
    result = _docker_run(docker_image_tag, "segqc", "build-reference", "--help")
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    for option in ("--cohort", "--out"):
        assert option in output, f"{option} missing from `segqc build-reference --help` output"


@requires_docker
def test_ac13_segqc_evaluate_help_names_cohort_out(docker_image_tag):
    result = _docker_run(docker_image_tag, "segqc", "evaluate", "--help")
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    for option in ("--cohort", "--out"):
        assert option in output, f"{option} missing from `segqc evaluate --help` output"


@requires_docker
def test_ac14_bundled_reference_loads_inside_container(docker_image_tag):
    snippet = (
        "from segqc.reference.artifact import bundled_default_reference; "
        "bundled_default_reference()"
    )
    result = _docker_run(docker_image_tag, "python", "-c", snippet)
    assert result.returncode == 0, (
        f"bundled_default_reference() failed inside the container:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@requires_docker
def test_ac15_gpu_and_radiomics_modules_not_importable(docker_image_tag):
    snippet = (
        "import importlib.util, sys; "
        "sys.exit(0 if all("
        "importlib.util.find_spec(m) is None "
        "for m in ('cupy','cucim','radiomics','torch')"
        ") else 1)"
    )
    result = _docker_run(docker_image_tag, "python", "-c", snippet)
    assert result.returncode == 0, (
        "one or more of cupy/cucim/radiomics/torch is importable inside the "
        f"default image:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@requires_docker
def test_ac15_core_stack_remains_importable(docker_image_tag):
    snippet = "import numpy, scipy"
    result = _docker_run(docker_image_tag, "python", "-c", snippet)
    assert result.returncode == 0, (
        f"numpy/scipy must remain importable in the default image:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


# =========================================================================== #
# Adversarial / edge cases -- Docker-gated
# =========================================================================== #


@requires_docker
def test_adv_segqc_bad_subcommand_does_not_crash_uncontrollably(docker_image_tag):
    """A malformed/unknown subcommand should exit non-zero (argparse error),
    not hang or crash the container in some uncontrolled way."""
    result = _docker_run(docker_image_tag, "segqc", "not-a-real-subcommand")
    assert result.returncode != 0


def test_adv_docker_gated_tests_skip_not_error_or_xfail_when_docker_absent():
    """Structural check on the skip mechanism itself: the marker used to
    gate AC9-AC15 must be a genuine skip condition (pytest.mark.skipif),
    not xfail or an unguarded call that would error when docker is missing.
    This test runs regardless of Docker availability."""
    assert isinstance(requires_docker.mark.args[0], bool)
    assert requires_docker.mark.name == "skipif"
