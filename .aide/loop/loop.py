#!/usr/bin/env python3
"""loop — usage-gated supervisor for unattended AIDE roadmap runs.

Relaunches the human-gated ``/aide-run-roadmap`` command whenever Claude's usage
limits allow, so a long roadmap can make progress across the 5-hour and weekly
windows without a person watching. It reads **hard** usage numbers from the OAuth
usage endpoint (no output scraping) and decides RUN / WAIT / STOP_WEEKLY / ERR —
a 1:1 stdlib port of the old ``check_usage.ps1`` + ``watch_and_resume.bat`` pair.

Stdlib-only (``urllib``); config comes from the gitignored
``.aide/loop/loop.local.toml`` (see ``loop.local.toml.example``). The framework
ships the script; the caps and deadlines are personal.

Decision loop, each pass:
  0. If a ``stop_after`` deadline is set and reached, exit without restarting.
  1. Read usage → RUN / WAIT / STOP_WEEKLY / ERR.
  2. STOP_WEEKLY → weekly ceiling hit; exit.
     WAIT <secs> → 5-hour window exhausted; sleep until it resets.
     RUN        → run the command, then re-check after ``interval``.
     ERR        → couldn't read usage (e.g. stale token); run the command once
                  anyway — Claude Code refreshes the on-disk token for next pass.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
ANTHROPIC_VERSION = "2023-06-01"

DEFAULTS: Dict[str, object] = {
    "max_weekly_pct": 95.0,
    "daily_reserve_pct": 10.0,
    "max_session_pct": 98.0,
    "buffer_seconds": 30,
    "interval": 300,
    "wait_fallback": 900,
    "stop_after": "",
    "credentials_path": "",   # empty -> ~/.claude/.credentials.json
    "command": "",            # empty -> claude "/aide-run-roadmap"
}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _parse_toml(text: str) -> Dict[str, object]:
    """tomllib on 3.11+, else a tiny flat reader for the loop.local.toml subset."""
    try:
        import tomllib  # type: ignore
        return tomllib.loads(text).get("loop", {})
    except ModuleNotFoundError:
        pass
    import re
    out: Dict[str, object] = {}
    in_loop = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([A-Za-z0-9_.]+)\]$", line)
        if m:
            in_loop = m.group(1) == "loop"
            continue
        if not in_loop or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and value[0] in "\"'":
            out[key] = value[1:].split(value[0], 1)[0]
        else:
            token = value.split("#", 1)[0].strip()
            try:
                out[key] = int(token)
            except ValueError:
                try:
                    out[key] = float(token)
                except ValueError:
                    out[key] = token
    return out


def load_loop_config(path: Optional[Path] = None) -> Dict[str, object]:
    cfg = dict(DEFAULTS)
    path = path or (Path(__file__).resolve().parent / "loop.local.toml")
    if path.is_file():
        cfg.update(_parse_toml(path.read_text(encoding="utf-8")))
    return cfg


# --------------------------------------------------------------------------- #
# usage endpoint
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# decision (pure — testable)
# --------------------------------------------------------------------------- #
def _parse_iso(ts: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decide_action(usage: Dict[str, object], cfg: Dict[str, object],
                  now: Optional[_dt.datetime] = None) -> Tuple[str, Optional[int], float, float]:
    """Return (action, arg, five_pct, seven_pct).

    action is RUN | WAIT | STOP_WEEKLY. For WAIT, arg is the seconds to sleep.
    Mirrors check_usage.ps1: weekly ceiling is the smaller of max_weekly_pct and
    100 - daily_reserve_pct*ceil(days-until-weekly-reset).
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    five = float((usage.get("five_hour") or {}).get("utilization", 0))
    seven = float((usage.get("seven_day") or {}).get("utilization", 0))

    caps = []
    max_weekly = float(cfg.get("max_weekly_pct", 0) or 0)
    daily_reserve = float(cfg.get("daily_reserve_pct", 0) or 0)
    if max_weekly > 0:
        caps.append(max_weekly)
    if daily_reserve > 0:
        reset7 = _parse_iso(str((usage.get("seven_day") or {}).get("resets_at")))
        days_left = (reset7 - now).total_seconds() / 86400.0
        d = max(0, math.ceil(days_left))
        caps.append(100 - daily_reserve * d)
    if caps:
        effective = min(caps)
        if seven >= effective:
            return "STOP_WEEKLY", round(effective), five, seven

    max_session = float(cfg.get("max_session_pct", 100) or 100)
    if five >= max_session:
        buffer = int(cfg.get("buffer_seconds", 30) or 30)
        reset5 = _parse_iso(str((usage.get("five_hour") or {}).get("resets_at")))
        secs = int((reset5 - now).total_seconds()) + buffer
        return "WAIT", max(secs, buffer), five, seven

    return "RUN", None, five, seven


# --------------------------------------------------------------------------- #
# supervisor loop
# --------------------------------------------------------------------------- #
def _command(cfg: Dict[str, object]):
    raw = str(cfg.get("command") or "").strip()
    if raw:
        import shlex
        return shlex.split(raw)
    return ["claude", "/aide-run-roadmap"]


def _past_deadline(cfg: Dict[str, object], now: _dt.datetime) -> bool:
    raw = str(cfg.get("stop_after") or "").strip()
    if not raw:
        return False
    try:
        deadline = _parse_iso(raw) if "T" in raw or "-" in raw.split()[0] else None
        if deadline is None:
            deadline = _dt.datetime.fromisoformat(raw)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=now.tzinfo)
        return now >= deadline
    except (ValueError, IndexError):
        return False  # unparseable -> keep running rather than exit unexpectedly


def _log(msg: str) -> None:
    print(f"[{_dt.datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_forever(cfg: Dict[str, object]) -> int:
    command = _command(cfg)
    interval = int(cfg.get("interval", 300) or 300)
    wait_fallback = int(cfg.get("wait_fallback", 900) or 900)
    while True:
        now = _dt.datetime.now(_dt.timezone.utc)
        if _past_deadline(cfg, now):
            _log(f"Reached stop_after deadline ({cfg.get('stop_after')}). Not restarting.")
            return 0

        token = read_access_token(cfg)
        if not token:
            _log("Could not read usage (no access token). Running command to re-auth…")
            subprocess.run(command)
            time.sleep(interval)
            continue
        try:
            usage = fetch_usage(token)
            action, arg, five, seven = decide_action(usage, cfg, now)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            _log(f"Could not read usage ({exc}). Running command to re-auth…")
            subprocess.run(command)
            time.sleep(interval)
            continue

        if action == "STOP_WEEKLY":
            _log(f"Weekly usage {round(seven)}% >= {arg}% effective ceiling. Stopping.")
            return 0
        if action == "WAIT":
            _log(f"Session (5h) window exhausted ({round(five)}%). Waiting {arg}s for reset…")
            time.sleep(int(arg))
            continue
        _log(f"Usage OK (session {round(five)}%, weekly {round(seven)}%). Running command…")
        subprocess.run(command)
        _log(f"Command exited. Rechecking in {interval}s…")
        time.sleep(interval)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None, help="path to loop.local.toml")
    parser.add_argument("--once", action="store_true", help="evaluate usage once and print the decision, do not loop")
    args = parser.parse_args(argv)
    cfg = load_loop_config(args.config)
    if args.once:
        token = read_access_token(cfg)
        if not token:
            print("ERR no-access-token")
            return 0
        try:
            usage = fetch_usage(token)
        except (urllib.error.URLError, OSError) as exc:
            print(f"ERR {exc}")
            return 0
        action, arg, five, seven = decide_action(usage, cfg)
        print(action, arg if arg is not None else "", round(five), round(seven))
        return 0
    return run_forever(cfg)


if __name__ == "__main__":
    sys.exit(main())
