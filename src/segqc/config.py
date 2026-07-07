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
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Union

__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "SegQCConfigError",
    "HeuristicConfig",
    "default_config",
    "load_config",
    "default_config_path",
    "bundled_default_config",
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
    # Connected-components threshold (item 012).  Components with strictly fewer
    # voxels than this value are flagged as small fragments.  Default ``0`` means
    # no component is ever flagged (nothing is strictly below 0).
    "min_fragment_voxels": 0,
    # Per-rule heuristic configuration (item 026).  Each entry has the shape:
    #   <rule_id>:
    #     enabled: bool          # default True when absent
    #     params:                # optional; individual rules supply their own
    #       <key>: <value>       # defaults via config.rule_param(id, key, default)
    # An absent or empty "rules" section means all rules are enabled with
    # their built-in defaults.
    "rules": {},
    # Case-level verdict-aggregation policy (item 034).  Keys are read via
    # ``policy_param``.  An absent or empty "verdict" section leaves the
    # aggregator at pure severity dominance (``flag_escalation_count`` == 0,
    # i.e. disabled).
    "verdict": {},
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
    min_fragment_voxels:
        Connected-components fragment threshold (item 012). Components with
        strictly fewer voxels than this value are flagged as small fragments.
        Default ``0`` means no component is ever flagged.
    """

    schema_version: str
    min_foreground_voxels: int
    min_label_count: int
    min_fragment_voxels: int = 0
    # Per-rule config section (item 026).  Shape:
    #   { <rule_id>: { "enabled": bool, "params": { <key>: <value> } } }
    # Access via rule_enabled / rule_param / rule_params rather than directly.
    rules: Dict[str, Any] = field(default_factory=dict)
    # Case-level verdict-aggregation policy section (item 034).  Shape:
    #   { <policy_key>: <value> }, e.g. {"flag_escalation_count": 3}.
    # Access via policy_param rather than directly.
    verdict: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Per-rule accessors (item 026)
    # ------------------------------------------------------------------ #

    def rule_enabled(self, rule_id: str, default: bool = True) -> bool:
        """Return whether *rule_id* is enabled in the config.

        Reads ``rules[rule_id]["enabled"]``; returns *default* (``True``) when
        the rule section or the ``enabled`` key is absent.

        Parameters
        ----------
        rule_id:
            The rule identifier string (e.g. ``"bounds"``).
        default:
            Value returned when no entry exists for *rule_id*.

        Returns
        -------
        bool
        """
        rule_cfg = self.rules.get(rule_id, {})
        return rule_cfg.get("enabled", default)

    def rule_params(self, rule_id: str) -> Mapping[str, Any]:
        """Return the ``params`` sub-dict for *rule_id*, or an empty mapping.

        Parameters
        ----------
        rule_id:
            The rule identifier string.

        Returns
        -------
        Mapping[str, Any]
            The ``params`` dict from the config, or ``{}`` if absent.
        """
        rule_cfg = self.rules.get(rule_id, {})
        return rule_cfg.get("params", {})

    def rule_param(self, rule_id: str, key: str, default: Any) -> Any:
        """Return a single parameter value for *rule_id*, or *default*.

        Convenience accessor: reads ``rules[rule_id]["params"][key]``; returns
        *default* when the rule section, ``params``, or *key* is absent.

        Parameters
        ----------
        rule_id:
            The rule identifier string (e.g. ``"bounds"``).
        key:
            The parameter name within the rule's ``params`` block.
        default:
            Value returned when the key is absent at any level.

        Returns
        -------
        Any
        """
        return self.rule_params(rule_id).get(key, default)

    # ------------------------------------------------------------------ #
    # Verdict-aggregation policy accessor (item 034)
    # ------------------------------------------------------------------ #

    def policy_param(self, key: str, default: Any) -> Any:
        """Return a single verdict-aggregation policy value, or *default*.

        Convenience accessor: reads ``verdict[key]``; returns *default* when
        the ``verdict`` section or *key* is absent.

        Parameters
        ----------
        key:
            The policy parameter name (e.g. ``"flag_escalation_count"``).
        default:
            Value returned when the key is absent.

        Returns
        -------
        Any
        """
        return self.verdict.get(key, default)


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


def default_config_path() -> pathlib.Path:
    """Return the absolute path to the bundled ``default_config.yaml`` (item 035).

    This is the documented, versioned materialisation of every rule family's
    shipped code defaults plus the verdict-aggregation policy (see the file's
    own header comment). Resolved via ``importlib.resources`` -- the same
    pattern ``segqc.report._load_schema`` already uses for
    ``report_schema_v0.json`` -- so the path is correct both from the source
    tree and from an installed wheel.

    Returns
    -------
    pathlib.Path
        Absolute path to ``default_config.yaml`` inside the installed
        ``segqc`` package.
    """
    import importlib.resources as _pkg_resources

    import segqc as _segqc_pkg  # local import to avoid circular deps at module level

    ref = _pkg_resources.files(_segqc_pkg).joinpath("default_config.yaml")
    return pathlib.Path(str(ref))


def bundled_default_config() -> HeuristicConfig:
    """Return the :class:`HeuristicConfig` loaded from the bundled default file.

    Convenience wrapper equal to ``load_config(default_config_path())``. This
    is what ``segqc run`` loads when no ``--config`` flag is given (item 035).

    Returns
    -------
    HeuristicConfig
    """
    return load_config(default_config_path())
