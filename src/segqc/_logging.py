"""Structured logging helpers for the ``segqc`` package (item 005).

All ``segqc.*`` loggers are children of the top-level ``"segqc"`` logger, so
calling :func:`setup_logging` once is enough to configure the whole hierarchy.

Usage (in ``segqc`` modules)::

    import logging
    logger = logging.getLogger(__name__)   # e.g. "segqc.config", "segqc.io"
    logger.info("something happened")

Callers that want structured output::

    from segqc._logging import setup_logging
    setup_logging("DEBUG", json_format=True)

Design decisions (item 005)
----------------------------
- **Module name ``_logging`` not ``logging``**: naming the submodule
  ``segqc.logging`` would shadow the stdlib ``logging`` module from inside
  the package, causing subtle ``ImportError`` / wrong-module bugs. The
  private ``_logging`` name is importable by callers but signals that it is
  an implementation detail rather than a stable public API surface.
- **No global side-effects on import**: importing this module never
  installs handlers or changes logger levels. ``setup_logging`` is the
  explicit, idempotent call.
- **Idempotency**: calling ``setup_logging`` a second time (e.g. in tests
  that call it multiple times) removes all existing handlers before adding
  the new one, so the handler count stays at 1.
- **Formatter choice**: plain text for humans (default); JSON lines for
  machine consumers (XNAT container logs, log aggregators, test assertions).
  The JSON formatter emits one object per record with keys ``time``,
  ``level``, ``logger``, and ``message``.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Union

__all__ = ["setup_logging", "JsonFormatter"]

# The package-wide root logger. All ``segqc.*`` child loggers propagate here.
_PACKAGE_LOGGER_NAME = "segqc"

# Default format for the plain-text handler.
_PLAIN_FORMAT = "%(levelname)-8s  %(name)s — %(message)s"


class JsonFormatter(logging.Formatter):
    """Format each log record as a single JSON object on one line.

    Output fields (always present):

    ``time``
        ISO-8601-like timestamp (UTC) from the log record, e.g.
        ``"2024-01-15T12:34:56.789012"``.
    ``level``
        The level name, e.g. ``"INFO"``, ``"WARNING"``.
    ``logger``
        The logger name, e.g. ``"segqc.config"``.
    ``message``
        The formatted log message (the result of ``record.getMessage()``).
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        """Return a JSON-serialised string for *record*."""
        # formatTime with a None datefmt gives the default ISO-like format;
        # we strip the millisecond suffix that formatTime adds and reconstruct
        # microsecond precision from record.created.
        import datetime

        ts = datetime.datetime.utcfromtimestamp(record.created).isoformat()
        payload = {
            "time": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: Union[str, int] = "WARNING",
    *,
    json_format: bool = False,
) -> None:
    """Configure the ``"segqc"`` logger hierarchy.

    Sets the log level and installs exactly one :class:`logging.StreamHandler`
    writing to :data:`sys.stderr`. Calling this function more than once is safe
    (idempotent): existing handlers on the ``"segqc"`` logger are removed before
    the new handler is added, so handler duplication never occurs.

    This function has **no effect on import** — it must be called explicitly by
    the application entry point (the CLI in item 006 will call it after parsing
    ``--log-level``).

    Parameters
    ----------
    level:
        Log level for the ``"segqc"`` logger. Accepts the standard stdlib names
        (``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``)
        as strings or their integer equivalents (e.g. ``logging.DEBUG = 10``).
    json_format:
        If ``True``, use :class:`JsonFormatter` (one JSON object per line).
        If ``False`` (default), use a human-readable plain-text formatter.

    Raises
    ------
    ValueError
        If *level* is a string that is not a recognised log-level name. (This
        is the stdlib behaviour of ``logging.getLevelName`` / ``setLevel``.)
    """
    root = logging.getLogger(_PACKAGE_LOGGER_NAME)

    # Remove all existing handlers to guarantee idempotency.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if json_format:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(_PLAIN_FORMAT)

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Do not propagate to the root Python logger (avoids duplicate output if
    # the caller has also configured the root logger).
    root.propagate = False
