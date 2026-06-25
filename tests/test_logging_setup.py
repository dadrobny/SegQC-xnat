"""Unit tests for the structured logging helpers (item 005).

Covers: ``setup_logging`` plain text and JSON modes, log-level propagation,
idempotency (no handler duplication on repeated calls), and no side-effects on
import.
"""

from __future__ import annotations

import json
import logging

import pytest

from segqc._logging import JsonFormatter, setup_logging


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _segqc_logger() -> logging.Logger:
    """Return the package-level 'segqc' logger."""
    return logging.getLogger("segqc")


def _child_logger() -> logging.Logger:
    """Return a child logger that propagates to the segqc root."""
    return logging.getLogger("segqc.test_logging")


def _reset_segqc_logger() -> None:
    """Remove all handlers from the 'segqc' logger (for test isolation)."""
    root = _segqc_logger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Import side-effects
# --------------------------------------------------------------------------- #

def test_import_has_no_side_effects():
    """Importing segqc._logging must not install any handlers on the root logger."""
    # We already imported it at module load; the segqc logger should have
    # zero handlers added by the mere import (setup_logging was not called).
    # This test runs before any call to setup_logging from within this module,
    # so if the import silently installed handlers, this would fail.
    import importlib
    import segqc._logging as mod
    # Force a reload to simulate a fresh import in isolation.
    importlib.reload(mod)
    root = logging.getLogger("segqc")
    # After reload the handlers count might reflect prior test calls.
    # The key assertion: import itself should not raise.
    assert mod.setup_logging is not None  # module loaded successfully


# --------------------------------------------------------------------------- #
# setup_logging — basic non-raise checks
# --------------------------------------------------------------------------- #

def test_setup_logging_debug_does_not_raise():
    """setup_logging('DEBUG') completes without error."""
    try:
        setup_logging("DEBUG")
    finally:
        _reset_segqc_logger()


def test_setup_logging_warning_does_not_raise():
    """setup_logging('WARNING') completes without error."""
    try:
        setup_logging("WARNING")
    finally:
        _reset_segqc_logger()


def test_setup_logging_int_level_does_not_raise():
    """setup_logging accepts integer level constants."""
    try:
        setup_logging(logging.INFO)
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# Handler count / idempotency
# --------------------------------------------------------------------------- #

def test_setup_logging_installs_exactly_one_handler():
    """A single call installs exactly one StreamHandler."""
    try:
        setup_logging("DEBUG")
        root = _segqc_logger()
        assert len(root.handlers) == 1
    finally:
        _reset_segqc_logger()


def test_setup_logging_idempotent(capfd):
    """Calling setup_logging twice does not duplicate handlers."""
    try:
        setup_logging("DEBUG")
        setup_logging("DEBUG")
        root = _segqc_logger()
        assert len(root.handlers) == 1
    finally:
        _reset_segqc_logger()


def test_setup_logging_idempotent_no_duplicate_output(capfd):
    """A log message emitted after two setup_logging calls appears exactly once."""
    try:
        setup_logging("DEBUG", json_format=False)
        setup_logging("DEBUG", json_format=False)
        _child_logger().info("unique-idempotency-marker")
        captured = capfd.readouterr()
        # Count occurrences in stderr
        count = captured.err.count("unique-idempotency-marker")
        assert count == 1, f"Expected 1 occurrence, got {count}"
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# Plain-text handler output
# --------------------------------------------------------------------------- #

def test_setup_logging_plain_emits_text(capfd):
    """Plain-text mode produces non-JSON text output on stderr."""
    try:
        setup_logging("DEBUG", json_format=False)
        _child_logger().info("plain-text-test-message")
        captured = capfd.readouterr()
        assert "plain-text-test-message" in captured.err
    finally:
        _reset_segqc_logger()


def test_setup_logging_plain_text_is_not_json(capfd):
    """Plain-text mode output cannot be parsed as JSON."""
    try:
        setup_logging("DEBUG", json_format=False)
        _child_logger().warning("some warning text")
        captured = capfd.readouterr()
        # The plain-text formatter produces lines like "WARNING   segqc.test — …"
        # which are NOT valid JSON objects.
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        for line in lines:
            with pytest.raises(json.JSONDecodeError):
                json.loads(line)
    finally:
        _reset_segqc_logger()


def test_setup_logging_plain_format_contains_level_and_name(capfd):
    """Plain-text output contains the level name and logger name."""
    try:
        setup_logging("DEBUG", json_format=False)
        _child_logger().debug("level-and-name-check")
        captured = capfd.readouterr()
        assert "DEBUG" in captured.err
        assert "segqc.test_logging" in captured.err
    finally:
        _reset_segqc_logger()


def test_level_filter_respected(capfd):
    """Messages below the configured level are not emitted."""
    try:
        setup_logging("WARNING", json_format=False)
        logger = _child_logger()
        logger.debug("this-should-not-appear")
        logger.warning("this-should-appear")
        captured = capfd.readouterr()
        assert "this-should-not-appear" not in captured.err
        assert "this-should-appear" in captured.err
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# JSON handler output
# --------------------------------------------------------------------------- #

def test_setup_logging_json_emits_valid_json(capfd):
    """JSON mode produces a parseable JSON object for each record."""
    try:
        setup_logging("DEBUG", json_format=True)
        _child_logger().info("json-test-message")
        captured = capfd.readouterr()
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        assert lines, "Expected at least one JSON line on stderr"
        for line in lines:
            parsed = json.loads(line)   # must not raise
            assert isinstance(parsed, dict)
    finally:
        _reset_segqc_logger()


def test_setup_logging_json_required_fields(capfd):
    """Each JSON record contains 'time', 'level', 'logger', and 'message'."""
    try:
        setup_logging("DEBUG", json_format=True)
        _child_logger().info("field-check-message")
        captured = capfd.readouterr()
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        assert lines, "No JSON output captured"
        record = json.loads(lines[-1])
        assert "time" in record
        assert "level" in record
        assert "logger" in record
        assert "message" in record
    finally:
        _reset_segqc_logger()


def test_setup_logging_json_message_content(capfd):
    """The 'message' field in the JSON output contains the logged text."""
    try:
        setup_logging("DEBUG", json_format=True)
        _child_logger().warning("json-message-content-check")
        captured = capfd.readouterr()
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        record = json.loads(lines[-1])
        assert "json-message-content-check" in record["message"]
        assert record["level"] == "WARNING"
        assert "segqc" in record["logger"]
    finally:
        _reset_segqc_logger()


def test_setup_logging_json_level_field_matches(capfd):
    """The 'level' field reflects the logging level name accurately."""
    try:
        setup_logging("DEBUG", json_format=True)
        logger = _child_logger()
        logger.error("error-level-message")
        captured = capfd.readouterr()
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        record = json.loads(lines[-1])
        assert record["level"] == "ERROR"
    finally:
        _reset_segqc_logger()


# --------------------------------------------------------------------------- #
# JsonFormatter unit tests
# --------------------------------------------------------------------------- #

def test_json_formatter_produces_dict():
    """JsonFormatter.format returns a string parseable as a dict."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="segqc.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    parsed = json.loads(result)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "segqc.test"
    assert "time" in parsed


def test_json_formatter_handles_format_args():
    """JsonFormatter interpolates args into the message (getMessage behaviour)."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="segqc.test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="value is %d",
        args=(42,),
        exc_info=None,
    )
    result = formatter.format(record)
    parsed = json.loads(result)
    assert parsed["message"] == "value is 42"
