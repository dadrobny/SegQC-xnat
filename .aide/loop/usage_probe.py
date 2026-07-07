#!/usr/bin/env python3
"""Claude-adapter usage probe — the Anthropic OAuth "usage" endpoint.

**Ownership.** This file is *Claude-adapter* code, not engine code. In the
standalone `aide-loop` framework repo it is owned by `adapters/claude/usage_probe.py`
and `install.py` copies it into a consumer's `.aide/loop/usage_probe.py`. The
engine's supervisor (`.aide/loop/loop.py`) is provider-agnostic: it loads whatever
`usage_probe.py` the installed adapter dropped next to it, selected by
`[loop] usage_probe` in `loop.local.toml`. A non-Claude runtime with no usage API
sets `usage_probe = "none"` and ships no probe; the loop then relaunches on a plain
time cadence. See `.aide/ADAPTER-SPEC.md` §"Optional: usage probe".

**Contract.** The engine only requires a module-level `get_usage(cfg) -> dict | None`.
It returns the raw usage document (with `five_hour`/`seven_day` utilisation +
`resets_at`) that the engine's `decide_action` interprets, or `None` when usage
cannot be read (no token, network error) — which the engine treats as "run on time
cadence" (for this probe that also re-auths, since Claude Code refreshes the
on-disk OAuth token when it runs).

Stdlib-only (`urllib`). Reads a **hard** usage number from the OAuth endpoint, no
output scraping.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
ANTHROPIC_VERSION = "2023-06-01"


def _credentials_path(cfg: Dict[str, object]) -> Path:
    raw = str(cfg.get("credentials_path") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".claude" / ".credentials.json"


def read_access_token(cfg: Dict[str, object]) -> Optional[str]:
    path = _credentials_path(cfg)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    token = (data.get("claudeAiOauth") or {}).get("accessToken")
    return token or None


def fetch_usage(token: str, timeout: int = 30) -> Dict[str, object]:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": OAUTH_BETA,
        "anthropic-version": ANTHROPIC_VERSION,
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode("utf-8"))


def get_usage(cfg: Dict[str, object]) -> Optional[Dict[str, object]]:
    """The engine-facing entry point. Returns the usage document or ``None``."""
    token = read_access_token(cfg)
    if not token:
        return None
    try:
        return fetch_usage(token)
    except (urllib.error.URLError, OSError, ValueError):
        return None
