"""Unit tests for the versioned heuristic-config scaffold (item 005).

Covers: ``default_config()``, ``load_config()`` with valid/invalid YAML files,
schema-version validation, default filling, and the ``SegQCConfigError``
exception surface.
"""

from __future__ import annotations

import pathlib

import pytest

from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    HeuristicConfig,
    SegQCConfigError,
    default_config,
    load_config,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    """Write *content* to a YAML file in *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# default_config
# --------------------------------------------------------------------------- #

def test_default_config_is_valid():
    """default_config() returns a HeuristicConfig with the supported version."""
    cfg = default_config()
    assert isinstance(cfg, HeuristicConfig)
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION


def test_default_config_placeholder_fields_are_zero():
    """Placeholder empty-detection fields default to 0 (no threshold applied)."""
    cfg = default_config()
    assert cfg.min_foreground_voxels == 0
    assert cfg.min_label_count == 0


def test_default_config_is_frozen():
    """HeuristicConfig is immutable after construction."""
    cfg = default_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.schema_version = "9.9"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# load_config — happy paths
# --------------------------------------------------------------------------- #

def test_load_minimal_yaml(tmp_path):
    """A config with only schema_version loads cleanly; defaults fill the rest."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION
    # Placeholder fields must be at their defaults (0).
    assert cfg.min_foreground_voxels == 0
    assert cfg.min_label_count == 0


def test_load_all_fields_explicit(tmp_path):
    """A config with every current field explicit round-trips the values."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 100\n"
        "min_label_count: 3\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION
    assert cfg.min_foreground_voxels == 100
    assert cfg.min_label_count == 3


def test_load_partial_fields_uses_defaults(tmp_path):
    """A config with only some fields fills missing ones from defaults."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 50\n"
        # min_label_count is absent — should fall back to 0
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == 50
    assert cfg.min_label_count == 0


def test_load_accepts_path_as_string(tmp_path):
    """load_config accepts a plain string path, not just pathlib.Path."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(str(p))
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION


def test_load_unknown_keys_are_ignored(tmp_path):
    """Fields not in the current schema are silently ignored (forward compat)."""
    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "future_field_not_yet_known: 999\n"
    )
    p = _write_yaml(tmp_path, content)
    cfg = load_config(p)  # must not raise
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION


def test_load_returns_heuristic_config_instance(tmp_path):
    """load_config always returns a HeuristicConfig, not a raw dict."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert isinstance(cfg, HeuristicConfig)


# --------------------------------------------------------------------------- #
# load_config — unsupported / missing schema_version
# --------------------------------------------------------------------------- #

def test_load_unsupported_version_raises(tmp_path):
    """A config with an unsupported schema_version raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "schema_version: '99.0'\n")
    with pytest.raises(SegQCConfigError, match="schema_version"):
        load_config(p)


def test_load_future_version_raises(tmp_path):
    """A 'future' schema version not yet supported raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "schema_version: '1.0'\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_missing_version_field_raises(tmp_path):
    """A config without any schema_version key raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "min_foreground_voxels: 10\n")
    with pytest.raises(SegQCConfigError, match="schema_version"):
        load_config(p)


def test_load_empty_version_string_raises(tmp_path):
    """An empty string schema_version raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "schema_version: ''\n")
    with pytest.raises(SegQCConfigError, match="schema_version"):
        load_config(p)


# --------------------------------------------------------------------------- #
# load_config — malformed YAML
# --------------------------------------------------------------------------- #

def test_load_malformed_yaml_raises(tmp_path):
    """Syntactically invalid YAML raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "key: [unclosed bracket\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_yaml_not_a_mapping_raises(tmp_path):
    """A YAML file whose top level is a list (not a mapping) raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "- item1\n- item2\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


def test_load_yaml_scalar_raises(tmp_path):
    """A YAML file whose top level is a bare scalar raises SegQCConfigError."""
    p = _write_yaml(tmp_path, "just a string\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


# --------------------------------------------------------------------------- #
# load_config — missing file
# --------------------------------------------------------------------------- #

def test_load_missing_file_raises(tmp_path):
    """A path to a non-existent file raises SegQCConfigError."""
    p = tmp_path / "does_not_exist.yaml"
    with pytest.raises(SegQCConfigError, match="not found"):
        load_config(p)


def test_load_missing_file_chains_original_exception(tmp_path):
    """The SegQCConfigError for a missing file chains the original FileNotFoundError."""
    p = tmp_path / "nonexistent.yaml"
    with pytest.raises(SegQCConfigError) as exc_info:
        load_config(p)
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


# --------------------------------------------------------------------------- #
# SegQCConfigError is raised, not raw exceptions
# --------------------------------------------------------------------------- #

def test_error_is_segqc_config_error_type(tmp_path):
    """All config errors are instances of SegQCConfigError, not raw exceptions."""
    # Malformed YAML — should not leak yaml.YAMLError directly
    p = _write_yaml(tmp_path, "bad: [unclosed\n")
    exc = None
    try:
        load_config(p)
    except SegQCConfigError as e:
        exc = e
    assert exc is not None, "Expected SegQCConfigError to be raised"


def test_segqc_config_error_is_exception_subclass():
    """SegQCConfigError is a subclass of Exception (catchable with 'except Exception')."""
    assert issubclass(SegQCConfigError, Exception)


def test_segqc_config_error_message_is_informative(tmp_path):
    """The SegQCConfigError message names the bad version."""
    p = _write_yaml(tmp_path, "schema_version: 'bad-version'\n")
    with pytest.raises(SegQCConfigError) as exc_info:
        load_config(p)
    assert "bad-version" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Integration: schema_version accessible for report embedding
# --------------------------------------------------------------------------- #

def test_schema_version_accessible_on_loaded_config(tmp_path):
    """schema_version is surfaced as an attribute for downstream callers (item 009)."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    # Attribute access (not dict lookup) is how downstream callers use it.
    version = cfg.schema_version
    assert isinstance(version, str)
    assert version == SUPPORTED_SCHEMA_VERSION
