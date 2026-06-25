"""Versioned heuristic-config scaffold for the ``segqc`` package (item 005).

This module provides the plumbing that Stage 4 heuristics will populate with
real thresholds. For now it ships a config schema with ``schema_version`` plus
**placeholder** empty-detection fields (``min_foreground_voxels``,
``min_label_count``) that item 007 will give meaning to.

Typical usage::

    from segqc.config import default_config, load_config, SegQCConfigError

    # No file — sensible defaults:
    cfg = default_config()

    # From a YAML file on disk:
    try:
        cfg = load_config("/path/to/segqc_config.yaml")
    except SegQCConfigError as exc:
        print(f"Config error: {exc}")

    # Embed in reports (item 009):
    print(cfg.schema_version)   # e.g. "0.1"

Design decisions (item 005)
----------------------------
1. **YAML chosen over JSON**: more human-friendly (allows comments, less noise).
   Added ``PyYAML`` to ``[project.dependencies]`` in ``pyproject.toml``.
2. **``schema_version`` — strict equality**: any version other than
   ``SUPPORTED_SCHEMA_VERSION`` raises ``SegQCConfigError``. Simple and safe
   for an early schema; the migration path is to bump the version string and
   update the loader (or add a compat shim) at that point.
3. **Missing-file error wrapped as ``SegQCConfigError``**: callers only need to
   catch one exception type for all config problems. The original
   ``FileNotFoundError`` is chained (``raise ... from exc``) for debuggability.
4. **Placeholder empty-detection field names** ``min_foreground_voxels`` and
   ``min_label_count`` default to ``0`` (i.e. "no threshold applied"). Item 007
   gives them real semantics; if it renames them, it updates this dataclass and
   the ``_DEFAULTS`` dict.
5. **``_DEFAULTS`` as the single source of truth**: ``default_config()`` and the
   merge logic in ``load_config`` both key off this dict, so adding a new field
   requires only one edit here.
6. **``HeuristicConfig`` is frozen**: immutable after construction, consistent
   with the ``@dataclass(frozen=True)`` style used in ``segqc.io`` and
   ``segqc.labels``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Union

__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "SegQCConfigError",
    "HeuristicConfig",
    "default_config",
    "load_config",
]

# The only schema version this loader accepts. Bump this string and provide a
# migration note in the item spec whenever the schema changes incompatibly.
SUPPORTED_SCHEMA_VERSION: str = "0.1"

# ---- Defaults --------------------------------------------------------------- #
# Single source of truth for every field's default value.  ``default_config()``
# and the merge step in ``load_config`` both read from here.
_DEFAULTS: Dict[str, Any] = {
    "schema_version": SUPPORTED_SCHEMA_VERSION,
    # Placeholder empty-detection thresholds (item 007 will give these meaning).
    # Default ``0`` means "no threshold applied" (every map passes).
    "min_foreground_voxels": 0,
    "min_label_count": 0,
}


# ---- Exception -------------------------------------------------------------- #

class SegQCConfigError(Exception):
    """Raised when a heuristic-config file is missing, malformed, or incompatible.

    Covers three cases:
    - File not found (wraps ``FileNotFoundError`` via exception chaining).
    - Syntactically invalid YAML / JSON.
    - ``schema_version`` field absent or not equal to
      :data:`SUPPORTED_SCHEMA_VERSION`.
    """


# ---- Data model ------------------------------------------------------------- #

@dataclass(frozen=True)
class HeuristicConfig:
    """Typed, immutable container for the heuristic-configuration values.

    Attributes
    ----------
    schema_version:
        The version string from the config file (or the baked-in default).
        Embedded in JSON reports (item 009) for reproducibility.
    min_foreground_voxels:
        **Placeholder** (item 007). Minimum number of foreground voxels before a
        segmentation is flagged as near-empty. Default ``0`` (no threshold).
    min_label_count:
        **Placeholder** (item 007). Minimum number of distinct labels before a
        segmentation is flagged as near-empty. Default ``0`` (no threshold).
    """

    schema_version: str
    min_foreground_voxels: int
    min_label_count: int


# ---- Public API ------------------------------------------------------------- #

def default_config() -> HeuristicConfig:
    """Return a :class:`HeuristicConfig` built entirely from the baked-in defaults.

    Useful for callers that do not need a config file (tests, CLI when no
    ``--config`` flag is provided).
    """
    return HeuristicConfig(**_DEFAULTS)


def load_config(path: Union[str, "pathlib.Path"]) -> HeuristicConfig:
    """Load a YAML heuristic-config file and return a validated :class:`HeuristicConfig`.

    Missing keys are filled from :data:`_DEFAULTS` (file values always win for
    present keys). The ``schema_version`` field is required and must equal
    :data:`SUPPORTED_SCHEMA_VERSION`.

    Parameters
    ----------
    path:
        Path to the YAML config file. Accepts ``str`` or
        :class:`pathlib.Path`.

    Returns
    -------
    HeuristicConfig

    Raises
    ------
    SegQCConfigError
        If the file does not exist, is syntactically invalid, or contains an
        unsupported ``schema_version``.
    """
    import yaml  # lazy import: only needed when a file is actually loaded

    path = pathlib.Path(path)

    # --- 1. Read the file ---------------------------------------------------- #
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SegQCConfigError(
            f"Config file not found: {path}"
        ) from exc

    # --- 2. Parse YAML ------------------------------------------------------- #
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise SegQCConfigError(
            f"Config file is not valid YAML: {path}\n{exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SegQCConfigError(
            f"Config file must be a YAML mapping (got {type(data).__name__!r}): {path}"
        )

    # --- 3. Validate schema_version ------------------------------------------ #
    version = data.get("schema_version")
    if version is None:
        raise SegQCConfigError(
            f"Config file is missing required field 'schema_version': {path}"
        )
    if version != SUPPORTED_SCHEMA_VERSION:
        raise SegQCConfigError(
            f"Unsupported config schema_version {version!r} in {path}. "
            f"This version of segqc supports schema_version={SUPPORTED_SCHEMA_VERSION!r}."
        )

    # --- 4. Merge file values over defaults ---------------------------------- #
    merged = dict(_DEFAULTS)
    for key, value in data.items():
        if key in merged:
            merged[key] = value
        # Unknown keys are silently ignored (forward-compatible reads of new
        # fields that an older loader doesn't know about).

    return HeuristicConfig(**merged)
