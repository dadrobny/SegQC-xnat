"""Tests for the XNAT Container Service ``command.json`` (item 067).

Pure JSON / structural validation only -- no Docker, no live XNAT server, no
``docker run``. Parses the repo-root ``command.json`` once (module-scoped
fixture) and asserts on the parsed structure per the pinned mount/argument
contract in ``docs/aide/items/067-xnat-container-service-command-json.md``.
Runs in the default fast suite (unlike item 066/069's Docker-gated tests).

One focused test per Acceptance Criterion, plus adversarial/edge-case tests
that exercise the checking *logic* itself (closure/orphan detection, path
normalisation, image-repository parsing) against small synthetic fixtures so
a future regression in ``command.json`` is caught loudly rather than by a
silently-too-lenient check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMAND_JSON_PATH = REPO_ROOT / "command.json"

REQUIRED_TOP_LEVEL_KEYS = (
    "name",
    "image",
    "type",
    "command-line",
    "mounts",
    "inputs",
    "outputs",
)

SCAN_MOUNT_PATH = "/input/scan"
SEG_MOUNT_PATH = "/input/seg"
OUTPUT_MOUNT_PATH = "/output"
CONFIG_MOUNT_PATH = "/input/config"
REFERENCE_MOUNT_PATH = "/input/reference"

REPORT_JSON_NAME = "segfacet_report.json"
REPORT_TXT_NAME = "segfacet_report.txt"

# Matches a mount-path-shaped token (``/input/<segment>`` or ``/output``) as a
# whole path component -- deliberately NOT a bare substring search, so
# ``/input/scan`` does not false-match inside ``/input/scan-x``.
MOUNT_PATH_TOKEN_RE = re.compile(r"/input/[A-Za-z0-9_-]+|/output(?![A-Za-z0-9_-])")


# =========================================================================== #
# Helpers
# =========================================================================== #


def _normalize_path(path: str) -> str:
    """Normalise a leading/trailing slash for path comparisons."""
    if not path:
        return path
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def _load_command_json() -> dict:
    return json.loads(COMMAND_JSON_PATH.read_text(encoding="utf-8"))


def _mounts_by_path(command: dict) -> dict:
    """Index ``mounts`` by normalised container path -> mount entry."""
    result = {}
    for mount in command.get("mounts", []):
        path = mount.get("path")
        if path is not None:
            result[_normalize_path(path)] = mount
    return result


def _mounts_by_name(command: dict) -> dict:
    return {m["name"]: m for m in command.get("mounts", []) if "name" in m}


def _image_repository(image: str) -> str:
    """Strip any registry/namespace prefix and trailing ``:tag``, returning
    the bare repository component (e.g. ``ghcr.io/org/segfacet:1.0`` ->
    ``segfacet``)."""
    last_segment = image.rsplit("/", 1)[-1]
    return last_segment.split(":", 1)[0]


def _mount_path_tokens_in_command_line(command_line: str) -> set:
    return set(MOUNT_PATH_TOKEN_RE.findall(command_line))


def _used_mount_paths_and_names(command: dict) -> tuple:
    """Return (paths referenced in command-line, names referenced by outputs
    or xnat-wrapper provides-files-for-command-mount)."""
    used_paths = _mount_path_tokens_in_command_line(command.get("command-line", ""))
    used_names = set()
    for output in command.get("outputs", []):
        mount_name = output.get("mount")
        if mount_name:
            used_names.add(mount_name)
    for wrapper in command.get("xnat", []):
        for derived in wrapper.get("derived-inputs", []):
            provided = derived.get("provides-files-for-command-mount")
            if provided:
                used_names.add(provided)
    return used_paths, used_names


def _find_input(command: dict, name: str):
    for inp in command.get("inputs", []):
        if inp.get("name") == name:
            return inp
    return None


def _find_output_name_for_file(command: dict, filename: str):
    for output in command.get("outputs", []):
        target = output.get("path") or output.get("glob") or ""
        if filename in target:
            return output.get("name")
    return None


@pytest.fixture(scope="module")
def command() -> dict:
    return _load_command_json()


# =========================================================================== #
# AC1  command.json present, non-empty, valid JSON object
# =========================================================================== #


def test_ac1_command_json_present_and_nonempty():
    assert COMMAND_JSON_PATH.is_file(), "command.json must exist at the repo root"
    text = COMMAND_JSON_PATH.read_text(encoding="utf-8")
    assert text.strip(), "command.json must not be empty"


def test_ac1_command_json_parses_as_object():
    parsed = _load_command_json()
    assert isinstance(parsed, dict), "command.json must parse into a JSON object"


# =========================================================================== #
# AC2  Required top-level keys present, with correct container types
# =========================================================================== #


@pytest.mark.parametrize("key", REQUIRED_TOP_LEVEL_KEYS)
def test_ac2_required_top_level_key_present(command, key):
    assert key in command, f"required top-level key {key!r} is missing"


def test_ac2_name_is_nonempty_string(command):
    assert isinstance(command["name"], str)
    assert command["name"].strip()


def test_ac2_mounts_inputs_outputs_are_lists(command):
    assert isinstance(command["mounts"], list)
    assert isinstance(command["inputs"], list)
    assert isinstance(command["outputs"], list)


# =========================================================================== #
# AC3  type == "docker"
# =========================================================================== #


def test_ac3_type_is_docker(command):
    assert command["type"] == "docker"


# =========================================================================== #
# AC4  image repository component is segfacet
# =========================================================================== #


def test_ac4_image_is_nonempty_string(command):
    assert isinstance(command["image"], str)
    assert command["image"].strip()


def test_ac4_image_repository_is_segfacet(command):
    assert _image_repository(command["image"]) == "segfacet"


# =========================================================================== #
# AC5  Read-only scan mount at /input/scan
# =========================================================================== #


def test_ac5_scan_mount_declared_read_only(command):
    mounts = _mounts_by_path(command)
    assert SCAN_MOUNT_PATH in mounts, "no mount declared at /input/scan"
    assert mounts[SCAN_MOUNT_PATH].get("writable", False) is False


# =========================================================================== #
# AC6  Read-only segmentation mount at /input/seg
# =========================================================================== #


def test_ac6_seg_mount_declared_read_only(command):
    mounts = _mounts_by_path(command)
    assert SEG_MOUNT_PATH in mounts, "no mount declared at /input/seg"
    assert mounts[SEG_MOUNT_PATH].get("writable", False) is False


# =========================================================================== #
# AC7  Writable output mount at /output
# =========================================================================== #


def test_ac7_output_mount_declared_writable(command):
    mounts = _mounts_by_path(command)
    assert OUTPUT_MOUNT_PATH in mounts, "no mount declared at /output"
    assert mounts[OUTPUT_MOUNT_PATH].get("writable") is True


def test_ac7_exactly_one_writable_mount_at_output_path(command):
    writable_at_output = [
        m
        for m in command.get("mounts", [])
        if _normalize_path(m.get("path", "")) == OUTPUT_MOUNT_PATH and m.get("writable") is True
    ]
    assert len(writable_at_output) == 1


# =========================================================================== #
# AC8  Read-only optional config/reference override mounts
# =========================================================================== #


def test_ac8_config_mount_declared_read_only(command):
    mounts = _mounts_by_path(command)
    assert CONFIG_MOUNT_PATH in mounts, "no mount declared at /input/config"
    assert mounts[CONFIG_MOUNT_PATH].get("writable", False) is False


def test_ac8_reference_mount_declared_read_only(command):
    mounts = _mounts_by_path(command)
    assert REFERENCE_MOUNT_PATH in mounts, "no mount declared at /input/reference"
    assert mounts[REFERENCE_MOUNT_PATH].get("writable", False) is False


# =========================================================================== #
# AC9  Command-line invokes the item-068 entry script at the pinned path
# =========================================================================== #


def test_ac9_command_line_invokes_entrypoint_script(command):
    assert "python /app/docker/entrypoint.py" in command["command-line"]


# =========================================================================== #
# AC10  Command-line passes the required mount roots
# =========================================================================== #


@pytest.mark.parametrize("mount_path", [SCAN_MOUNT_PATH, SEG_MOUNT_PATH, OUTPUT_MOUNT_PATH])
def test_ac10_command_line_passes_required_mount_root(command, mount_path):
    assert mount_path in command["command-line"]


# =========================================================================== #
# AC11  Command-line mount references are all declared (closure check)
# =========================================================================== #


def test_ac11_command_line_mount_references_all_declared(command):
    tokens = _mount_path_tokens_in_command_line(command["command-line"])
    assert tokens, "no mount-path tokens found in command-line"
    declared_paths = set(_mounts_by_path(command).keys())
    undeclared = tokens - declared_paths
    assert not undeclared, f"command-line references undeclared mount path(s): {undeclared}"


def test_ac11_closure_check_would_catch_undeclared_mount_reference():
    """Adversarial: prove the closure-check logic actually discriminates by
    running it against a deliberately-broken synthetic command-line that
    references a mount path never declared in ``mounts``."""
    broken_command_line = (
        "python /app/docker/entrypoint.py --scan-dir /input/scan --extra-dir /input/extra"
    )
    tokens = _mount_path_tokens_in_command_line(broken_command_line)
    declared_paths = {"/input/scan"}
    undeclared = tokens - declared_paths
    assert undeclared == {"/input/extra"}


# =========================================================================== #
# AC12  Output mount references are all declared
# =========================================================================== #


def test_ac12_output_mounts_all_declared(command):
    declared_names = set(_mounts_by_name(command).keys())
    for output in command.get("outputs", []):
        mount_name = output.get("mount")
        assert mount_name in declared_names, (
            f"output {output.get('name')!r} references undeclared mount {mount_name!r}"
        )


# =========================================================================== #
# AC13  No orphan mounts (mounts -> usage)
# =========================================================================== #


def test_ac13_no_orphan_mounts(command):
    used_paths, used_names = _used_mount_paths_and_names(command)
    for mount in command.get("mounts", []):
        name = mount.get("name")
        path = _normalize_path(mount.get("path", ""))
        referenced = path in used_paths or name in used_names
        assert referenced, f"mount {name!r} ({path}) is declared but never referenced"


def test_ac13_orphan_check_would_catch_unused_mount():
    """Adversarial: prove the orphan-check logic actually discriminates by
    running it against a synthetic command declaring a mount that is never
    referenced in command-line, outputs, or the xnat wrapper."""
    fake_command = {
        "command-line": "python /app/docker/entrypoint.py --scan-dir /input/scan",
        "mounts": [
            {"name": "scan-in", "path": "/input/scan"},
            {"name": "unused-in", "path": "/input/unused"},
        ],
        "outputs": [],
        "xnat": [],
    }
    used_paths, used_names = _used_mount_paths_and_names(fake_command)
    orphans = [
        m["name"]
        for m in fake_command["mounts"]
        if _normalize_path(m["path"]) not in used_paths and m["name"] not in used_names
    ]
    assert orphans == ["unused-in"]


# =========================================================================== #
# AC14  JSON report output declared
# =========================================================================== #


def test_ac14_json_report_output_declared(command):
    outputs = command.get("outputs", [])
    matches = [o for o in outputs if REPORT_JSON_NAME in (o.get("path") or o.get("glob") or "")]
    assert matches, f"no output targets {REPORT_JSON_NAME}"
    output_mount_name = _mounts_by_path(command)[OUTPUT_MOUNT_PATH]["name"]
    assert any(o.get("mount") == output_mount_name for o in matches)


# =========================================================================== #
# AC15  Human report output declared, separately
# =========================================================================== #


def test_ac15_human_report_output_declared_separately(command):
    outputs = command.get("outputs", [])
    json_matches = [o for o in outputs if REPORT_JSON_NAME in (o.get("path") or o.get("glob") or "")]
    txt_matches = [o for o in outputs if REPORT_TXT_NAME in (o.get("path") or o.get("glob") or "")]
    assert txt_matches, f"no output targets {REPORT_TXT_NAME}"
    json_names = {o.get("name") for o in json_matches}
    txt_names = {o.get("name") for o in txt_matches}
    assert not (json_names & txt_names), "JSON and TXT reports must be distinct output entries"
    output_mount_name = _mounts_by_path(command)[OUTPUT_MOUNT_PATH]["name"]
    assert any(o.get("mount") == output_mount_name for o in txt_matches)


# =========================================================================== #
# AC16  reference-mode input renders --reference
# =========================================================================== #


def test_ac16_reference_mode_input_renders_reference_flag(command):
    inp = _find_input(command, "reference-mode")
    assert inp is not None, "no input named 'reference-mode' declared"
    assert inp.get("type") == "boolean"
    assert inp.get("true-value") == "--reference"
    assert inp.get("false-value", "") == ""
    replacement_key = inp.get("replacement-key")
    assert replacement_key, "reference-mode input must declare a replacement-key"
    assert replacement_key in command["command-line"]


# =========================================================================== #
# AC17  intensity-mode input renders --intensity
# =========================================================================== #


def test_ac17_intensity_mode_input_renders_intensity_flag(command):
    inp = _find_input(command, "intensity-mode")
    assert inp is not None, "no input named 'intensity-mode' declared"
    assert inp.get("type") == "boolean"
    assert inp.get("true-value") == "--intensity"
    assert inp.get("false-value", "") == ""
    replacement_key = inp.get("replacement-key")
    assert replacement_key, "intensity-mode input must declare a replacement-key"
    assert replacement_key in command["command-line"]


# =========================================================================== #
# AC18  File-override -> CLI-flag mapping documented
# =========================================================================== #


def test_ac18_config_override_documents_config_flag(command):
    config_mount = _mounts_by_path(command)[CONFIG_MOUNT_PATH]
    assert "--config" in json.dumps(config_mount), (
        "the /input/config mount declaration must document the --config flag it maps to"
    )


def test_ac18_reference_override_documents_reference_artifact_flag(command):
    reference_mount = _mounts_by_path(command)[REFERENCE_MOUNT_PATH]
    assert "--reference-artifact" in json.dumps(reference_mount), (
        "the /input/reference mount declaration must document the --reference-artifact flag"
    )


# =========================================================================== #
# AC19  XNAT wrapper establishes a session/scan context
# =========================================================================== #


def test_ac19_xnat_wrapper_has_session_or_scan_external_input(command):
    wrappers = command.get("xnat", [])
    assert wrappers, "command.json must declare an 'xnat' array with >=1 wrapper"
    wrapper = wrappers[0]
    external_inputs = wrapper.get("external-inputs", [])
    assert external_inputs, "xnat wrapper must declare at least one external-input"
    types = {str(ext.get("type", "")).lower() for ext in external_inputs}
    assert any(t in ("session", "scan") for t in types), (
        f"expected an external-input establishing session/scan context, got types {types}"
    )


# =========================================================================== #
# AC20  Wrapper derived-inputs provide the scan and seg mounts
# =========================================================================== #


def test_ac20_derived_inputs_provide_scan_and_seg_mounts(command):
    wrapper = command["xnat"][0]
    derived_inputs = wrapper.get("derived-inputs", [])
    assert derived_inputs, "xnat wrapper must declare derived-inputs"
    provided_mounts = {d.get("provides-files-for-command-mount") for d in derived_inputs}
    scan_mount_name = _mounts_by_path(command)[SCAN_MOUNT_PATH]["name"]
    seg_mount_name = _mounts_by_path(command)[SEG_MOUNT_PATH]["name"]
    assert scan_mount_name in provided_mounts, (
        f"no derived-input provides-files-for-command-mount for scan mount {scan_mount_name!r}"
    )
    assert seg_mount_name in provided_mounts, (
        f"no derived-input provides-files-for-command-mount for seg mount {seg_mount_name!r}"
    )


# =========================================================================== #
# AC21  Wrapper output-handlers accept both report outputs
# =========================================================================== #


def test_ac21_output_handlers_accept_both_report_outputs(command):
    wrapper = command["xnat"][0]
    handlers = wrapper.get("output-handlers", [])
    assert handlers, "xnat wrapper must declare output-handlers"
    accepted = {h.get("accepts-command-output") for h in handlers}
    json_output_name = _find_output_name_for_file(command, REPORT_JSON_NAME)
    txt_output_name = _find_output_name_for_file(command, REPORT_TXT_NAME)
    assert json_output_name is not None
    assert txt_output_name is not None
    assert json_output_name in accepted, (
        f"no output-handler accepts the JSON report output {json_output_name!r}"
    )
    assert txt_output_name in accepted, (
        f"no output-handler accepts the human report output {txt_output_name!r}"
    )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_extra_top_level_keys_do_not_break_required_key_check():
    """Optional top-level keys (label, description, version, schema-version,
    environment-variables) alongside the required seven must not defeat the
    required-key check."""
    fake_command = {
        "name": "segfacet",
        "image": "segfacet:latest",
        "type": "docker",
        "command-line": "python /app/docker/entrypoint.py",
        "mounts": [],
        "inputs": [],
        "outputs": [],
        "label": "FACET",
        "description": "Vertebra segmentation QC",
        "version": "1.0.0",
        "schema-version": "1.0",
        "environment-variables": {},
    }
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in fake_command


def test_adv_mount_path_token_scan_does_not_false_match_substring():
    """/input/scan must not be satisfied by /input/scan-x appearing in
    command-line -- the token regex must match whole path components."""
    command_line = "python /app/docker/entrypoint.py --scan-dir /input/scan-x --out-dir /output"
    tokens = _mount_path_tokens_in_command_line(command_line)
    assert "/input/scan-x" in tokens
    assert "/input/scan" not in tokens


def test_adv_normalize_path_handles_trailing_slash():
    assert _normalize_path("/output/") == "/output"
    assert _normalize_path("/input/scan") == "/input/scan"
    assert _normalize_path("output") == "/output"


def test_adv_image_repository_parse_handles_registry_prefix():
    assert _image_repository("ghcr.io/org/segfacet:1.0") == "segfacet"
    assert _image_repository("segfacet:latest") == "segfacet"
    assert _image_repository("segfacet") == "segfacet"
    assert _image_repository("registry:5000/segfacet:2.0") == "segfacet"


def test_adv_image_repository_rejects_unrelated_image():
    assert _image_repository("some-other-tool:latest") != "segfacet"


def test_adv_malformed_json_raises_clear_parse_error(tmp_path):
    bad_file = tmp_path / "bad_command.json"
    bad_file.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad_file.read_text(encoding="utf-8"))


def test_adv_missing_required_key_is_detected():
    fake_command = {k: ("x" if k not in ("mounts", "inputs", "outputs") else []) for k in REQUIRED_TOP_LEVEL_KEYS}
    del fake_command["mounts"]
    missing = [k for k in REQUIRED_TOP_LEVEL_KEYS if k not in fake_command]
    assert missing == ["mounts"]


def test_adv_wrong_type_value_is_detected():
    fake_command = {"type": "singularity"}
    assert fake_command["type"] != "docker"


def test_adv_wrong_container_type_for_mounts_is_detected():
    """mounts/inputs/outputs must be JSON arrays, not e.g. a single object."""
    fake_command = {"mounts": {"name": "scan-in", "path": "/input/scan"}}
    assert not isinstance(fake_command["mounts"], list)
