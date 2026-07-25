"""Deployment-documentation content checks (item 070, AC1-AC6).

Pure file-read / token-presence checks against ``docs/deployment.md`` -- no
Docker, no live XNAT server. Full prose cannot be asserted verbatim, so each
Acceptance Criterion asserts the doc exists and mentions the required
topic/command tokens (case-insensitive where sensible), per
``docs/aide/items/070-deployment-docs-stage-9-integration.md``.

NOTE (expected test-first failure): ``docs/deployment.md`` does not exist yet
at the time these tests are written -- the builder writes it in a later step.
Every test in this module is expected to fail until the doc lands; this is
the intended test-first order for this item.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_DOC_PATH = REPO_ROOT / "docs" / "deployment.md"
COMMAND_JSON_PATH = REPO_ROOT / "command.json"

MOUNT_PATHS = ("/input/scan", "/input/seg", "/output")
REPORT_FILENAMES = ("segfacet_report.json", "segfacet_report.txt")


# =========================================================================== #
# Helpers
# =========================================================================== #


def _read_doc_text() -> str:
    return DEPLOYMENT_DOC_PATH.read_text(encoding="utf-8")


def _live_command_json_mount_paths() -> set:
    """Cross-check helper for AC6: derive the mount paths the *live*
    command.json actually declares, so drift between the doc and the real
    artifact is caught rather than a hardcoded string in this test module."""
    command = json.loads(COMMAND_JSON_PATH.read_text(encoding="utf-8"))
    return {m["path"] for m in command.get("mounts", []) if "path" in m}


@pytest.fixture(scope="module")
def doc_text() -> str:
    return _read_doc_text()


# =========================================================================== #
# AC1  deployment doc exists, non-empty, readable UTF-8, non-trivial length
# =========================================================================== #


def test_ac1_deployment_doc_exists():
    assert DEPLOYMENT_DOC_PATH.is_file(), "docs/deployment.md must exist"


def test_ac1_deployment_doc_is_nonempty_and_nontrivial():
    text = _read_doc_text()
    assert text.strip(), "docs/deployment.md must not be empty"
    assert len(text.strip()) > 200, "docs/deployment.md must be of non-trivial length"


def test_ac1_deployment_doc_is_readable_utf8():
    # read_text with encoding="utf-8" itself raises UnicodeDecodeError on
    # invalid UTF-8; reaching this assertion proves the file decoded cleanly.
    text = _read_doc_text()
    assert isinstance(text, str)


# =========================================================================== #
# AC2  building-the-image documented
# =========================================================================== #


def test_ac2_default_build_command_documented(doc_text):
    lowered = doc_text.lower()
    assert "docker build" in lowered, "must document a docker build command"
    assert "-t segfacet:latest" in lowered or "-t segfacet" in lowered, (
        "must document tagging the default image (e.g. docker build -t segfacet:latest .)"
    )


def test_ac2_radiomics_build_arg_documented(doc_text):
    assert "INSTALL_RADIOMICS" in doc_text, (
        "must document the radiomics-enabled build variant via INSTALL_RADIOMICS"
    )


# =========================================================================== #
# AC3  installing command.json on XNAT documented, with an official reference
# =========================================================================== #


def test_ac3_command_json_install_on_xnat_documented(doc_text):
    assert "command.json" in doc_text, "must document installing command.json"
    assert "XNAT" in doc_text, "must mention XNAT in the install context"


def test_ac3_official_xnat_container_service_reference_present(doc_text):
    assert "wiki.xnat.org" in doc_text, (
        "must link the official XNAT Container Service documentation "
        "(a wiki.xnat.org URL)"
    )


# =========================================================================== #
# AC4  configuring inputs on an XNAT session documented
# =========================================================================== #


def test_ac4_session_input_tokens_documented(doc_text):
    lowered = doc_text.lower()
    assert "scan" in lowered, "must name the scan resource"
    assert ("segmentation" in lowered) or ("seg" in lowered), (
        "must name the segmentation resource"
    )
    assert "reference" in lowered, "must mention the reference-mode toggle/override"
    assert "intensity" in lowered, "must mention the intensity-mode toggle"


# =========================================================================== #
# AC5  troubleshooting common failure modes documented
# =========================================================================== #


def test_ac5_troubleshooting_section_present(doc_text):
    assert ("troubleshoot" in doc_text.lower()), (
        "must have a troubleshooting section (token 'troubleshoot'/'Troubleshooting')"
    )


def test_ac5_failure_modes_covered(doc_text):
    lowered = doc_text.lower()
    assert "missing" in lowered or "empty" in lowered, "must cover a missing/empty input mount"
    assert "ambiguous" in lowered or "multiple" in lowered, (
        "must cover an ambiguous (multiple-file) input mount"
    )
    assert "nifti" in lowered, "must cover a non-NIfTI input"


def test_ac5_failure_convention_documented(doc_text):
    assert "Error:" in doc_text, "must state failures surface as an 'Error:' message"
    lowered = doc_text.lower()
    assert "non-zero" in lowered or "nonzero" in lowered, (
        "must state failures exit with a non-zero exit code"
    )
    assert "traceback" in lowered, (
        "must state failures do not surface as a raw traceback"
    )


# =========================================================================== #
# AC6  mount/output contract documented and consistent with command.json
# =========================================================================== #


@pytest.mark.parametrize("mount_path", MOUNT_PATHS)
def test_ac6_mount_path_named(doc_text, mount_path):
    assert mount_path in doc_text, f"doc must name the mount path {mount_path}"


@pytest.mark.parametrize("filename", REPORT_FILENAMES)
def test_ac6_report_filename_named(doc_text, filename):
    assert filename in doc_text, f"doc must name the output report filename {filename}"


def test_ac6_documented_mount_paths_match_live_command_json():
    """Adversarial/consistency: fails loudly if the doc's named mount paths
    ever drift from what the live command.json actually declares, rather
    than being checked against a hardcoded string in this test module."""
    doc_text = _read_doc_text()
    live_mount_paths = _live_command_json_mount_paths()
    required_live_paths = {"/input/scan", "/input/seg", "/output"}
    assert required_live_paths <= live_mount_paths, (
        "command.json no longer declares the expected scan/seg/output mounts "
        "-- this test's assumptions are stale"
    )
    for mount_path in required_live_paths:
        assert mount_path in doc_text, (
            f"docs/deployment.md must name mount path {mount_path!r}, which "
            f"command.json currently declares"
        )
