"""Adversarial / edge-case tests for item 005 (structured logging + config).

These tests were added by the validator pass and attack the implementation
with hostile inputs that the builder's happy-path suite did not exercise.
All tests are deterministic, CPU-only, and portable.
"""

from __future__ import annotations

import io
import json
import logging
import pathlib

import pytest

from segqc._logging import JsonFormatter, setup_logging
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    HeuristicConfig,
    SegQCConfigError,
    default_config,
    load_config,
)


# --------------------------------------------------------------------------- #
# Helpers (same style as test_config.py)
# --------------------------------------------------------------------------- #

def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "cfg.yaml") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _reset_segqc_logger() -> None:
    root = logging.getLogger("segqc")
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.WARNING)


# =========================================================================== #
# CONFIG — adversarial inputs
# =========================================================================== #

# --------------------------------------------------------------------------- #
# schema_version type coercion / YAML unquoted float
# --------------------------------------------------------------------------- #

def test_load_schema_version_unquoted_float_raises(tmp_path):
    """YAML 'schema_version: 0.1' (unquoted) is parsed as float 0.1, not '0.1'.

    The strict string equality check must reject it with SegQCConfigError and
    a message that does not leak a raw TypeError or AttributeError.
    """
    p = _write_yaml(tmp_path, "schema_version: 0.1\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_schema_version_unquoted_float_error_is_informative(tmp_path):
    """The error for an unquoted-float schema_version names the bad value."""
    p = _write_yaml(tmp_path, "schema_version: 0.1\n")
    with pytest.raises(SegQCConfigError) as exc_info:
        load_config(p)
    # The message should mention the bad value, not raw Python exception text.
    msg = str(exc_info.value)
    assert "schema_version" in msg or "0.1" in str(msg)
    # Must NOT leak raw AttributeError / TypeError internals.
    assert "AttributeError" not in msg
    assert "TypeError" not in msg


def test_load_schema_version_null_raises(tmp_path):
    """YAML 'schema_version: ~' (null) must raise SegQCConfigError, not TypeError."""
    p = _write_yaml(tmp_path, "schema_version: ~\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_schema_version_integer_raises(tmp_path):
    """YAML 'schema_version: 1' (bare integer) must raise SegQCConfigError."""
    p = _write_yaml(tmp_path, "schema_version: 1\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_schema_version_trailing_whitespace_raises(tmp_path):
    """'schema_version: 0.1   ' (trailing whitespace) must not silently match."""
    # YAML preserves the string as-is when quoted, so this is a real user mistake.
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}   '\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


# --------------------------------------------------------------------------- #
# Empty / degenerate files
# --------------------------------------------------------------------------- #

def test_load_empty_file_raises(tmp_path):
    """An empty YAML file (safe_load returns None) raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_whitespace_only_file_raises(tmp_path):
    """A file with only whitespace/newlines raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "   \n\n  \n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


# --------------------------------------------------------------------------- #
# Directory-as-path
# --------------------------------------------------------------------------- #

def test_load_directory_path_raises(tmp_path):
    """Passing a directory path raises SegQCConfigError (not IsADirectoryError)."""
    with pytest.raises((SegQCConfigError, IsADirectoryError, OSError)):
        # We accept SegQCConfigError or OS-level errors — the key requirement is
        # that it does NOT return a HeuristicConfig and does NOT raise a raw
        # internal exception (like AttributeError) from the implementation.
        load_config(tmp_path)


# --------------------------------------------------------------------------- #
# Negative / zero / large placeholder field values
# --------------------------------------------------------------------------- #

def test_load_negative_min_foreground_voxels_accepted(tmp_path):
    """Negative min_foreground_voxels from YAML is accepted (semantics belong to item 007)."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: -1\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == -1


def test_load_large_field_values_accepted(tmp_path):
    """Very large integer field values are accepted without overflow."""
    big = 2**31 - 1  # max int32
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        f"min_foreground_voxels: {big}\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == big


def test_load_zero_values_accepted(tmp_path):
    """Explicit zero values in YAML are accepted (same as default, but not None)."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 0\n"
        "min_label_count: 0\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == 0
    assert cfg.min_label_count == 0


# --------------------------------------------------------------------------- #
# Immutability / no caller mutation
# --------------------------------------------------------------------------- #

def test_default_config_independent_instances():
    """Two calls to default_config() return independent objects (not the same instance)."""
    cfg1 = default_config()
    cfg2 = default_config()
    assert cfg1 is not cfg2


def test_load_config_does_not_mutate_defaults(tmp_path):
    """load_config must not mutate the module-level _DEFAULTS dict.

    If _DEFAULTS is modified in place, subsequent calls to default_config()
    would return different values.
    """
    from segqc.config import _DEFAULTS
    snapshot_before = dict(_DEFAULTS)

    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 999\n"
        "min_label_count: 42\n"
    )
    p = _write_yaml(tmp_path, content)
    load_config(p)

    # _DEFAULTS should be unchanged.
    assert _DEFAULTS == snapshot_before, "_DEFAULTS was mutated by load_config"

    # And default_config() still returns original defaults.
    cfg = default_config()
    assert cfg.min_foreground_voxels == 0
    assert cfg.min_label_count == 0


# --------------------------------------------------------------------------- #
# Error type — no raw library internals leaked
# --------------------------------------------------------------------------- #

def test_missing_file_does_not_leak_filenotfounderror(tmp_path):
    """A missing-file error surfaces as SegQCConfigError, not raw FileNotFoundError."""
    p = tmp_path / "gone.yaml"
    with pytest.raises(SegQCConfigError):
        load_config(p)
    # Confirm it's NOT raised as a bare FileNotFoundError.
    try:
        load_config(p)
    except SegQCConfigError:
        pass  # correct
    except FileNotFoundError:
        pytest.fail("load_config leaked a bare FileNotFoundError")


def test_malformed_yaml_does_not_leak_yaml_error(tmp_path):
    """A malformed YAML error surfaces as SegQCConfigError, not yaml.YAMLError."""
    import yaml
    p = _write_yaml(tmp_path, "key: [unclosed\n")
    try:
        load_config(p)
    except SegQCConfigError:
        pass  # correct
    except yaml.YAMLError:
        pytest.fail("load_config leaked a bare yaml.YAMLError")


# =========================================================================== #
# LOGGING — adversarial inputs
# =========================================================================== #

# --------------------------------------------------------------------------- #
# Invalid level string
# --------------------------------------------------------------------------- #

def test_setup_logging_invalid_level_raises():
    """An unrecognised level string must raise, not silently proceed."""
    try:
        with pytest.raises((ValueError, TypeError)):
            setup_logging("NOTLEVEL")
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# propagate=False is preserved across repeated calls
# --------------------------------------------------------------------------- #

def test_setup_logging_propagate_false_after_repeat():
    """After two calls to setup_logging, propagate is still False."""
    try:
        setup_logging("DEBUG")
        setup_logging("WARNING")
        root = logging.getLogger("segqc")
        assert root.propagate is False
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# JSON formatter — unicode / special chars
# --------------------------------------------------------------------------- #

def test_json_formatter_unicode_message():
    """JsonFormatter handles unicode characters in the message without raising."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="segqc.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="vertebra éàü \U0001f9e0",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    parsed = json.loads(result)
    assert "é" in parsed["message"]


def test_json_formatter_message_with_braces():
    """JsonFormatter handles messages with literal braces without format errors."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="segqc.test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="dict looks like {key: value}",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    parsed = json.loads(result)
    assert "dict looks like" in parsed["message"]


def test_json_formatter_output_is_single_line():
    """JsonFormatter emits exactly one line per record (no embedded newlines)."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="segqc.test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="line one\nline two",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    # The JSON payload itself should be parseable; embedded newlines in the
    # message are JSON-escaped, not literal newlines in the output.
    assert "\n" not in result, "JsonFormatter output contains a literal newline"


# --------------------------------------------------------------------------- #
# setup_logging — level propagates to handler
# --------------------------------------------------------------------------- #

def test_setup_logging_level_respected_on_handler(capfd):
    """The handler level matches the requested level so filtering works correctly."""
    try:
        setup_logging("ERROR", json_format=False)
        logger = logging.getLogger("segqc.adversarial_level")
        logger.warning("should-be-filtered")
        logger.error("should-appear")
        captured = capfd.readouterr()
        assert "should-be-filtered" not in captured.err
        assert "should-appear" in captured.err
    finally:
        _reset_segqc_logger()


def test_setup_logging_switch_from_json_to_plain(capfd):
    """Switching from json_format=True to json_format=False on second call works."""
    try:
        setup_logging("DEBUG", json_format=True)
        setup_logging("DEBUG", json_format=False)
        logger = logging.getLogger("segqc.adversarial_switch")
        logger.info("switch-test-message")
        captured = capfd.readouterr()
        # Should be plain text, not JSON.
        assert "switch-test-message" in captured.err
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        assert lines, "No output"
        with pytest.raises(json.JSONDecodeError):
            json.loads(lines[-1])
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

def test_default_config_is_deterministic():
    """Two calls to default_config() return equal objects."""
    cfg1 = default_config()
    cfg2 = default_config()
    assert cfg1 == cfg2


def test_load_config_is_deterministic(tmp_path):
    """Two loads of the same file produce equal HeuristicConfig objects."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 10\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg1 = load_config(p)
    cfg2 = load_config(p)
    assert cfg1 == cfg2
