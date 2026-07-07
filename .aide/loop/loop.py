#!/usr/bin/env python3
"""loop — usage-gated supervisor for unattended AIDE roadmap runs (engine).

Relaunches the human-gated ``/aide-run-roadmap`` command whenever usage limits
allow, so a long roadmap can make progress across a provider's rate windows
without a person watching. It reads **hard** usage numbers from a *pluggable
usage probe* (no output scraping) and decides RUN / WAIT / STOP_WEEKLY.

**Provider-agnostic.** This is engine code: it contains no Anthropic/Claude
specifics. The usage numbers come from an adapter-supplied ``usage_probe.py``
sitting next to this file, selected by ``[loop] usage_probe`` in
``loop.local.toml`` (``"anthropic-oauth"`` for the Claude adapter, ``"none"`` for
any runtime lacking a usage API). A probe exposes ``get_usage(cfg) -> dict | None``
and this module interprets the dict; see ``.aide/ADAPTER-SPEC.md``.

Stdlib-only; config comes from the gitignored ``.aide/loop/loop.local.toml`` (see
``loop.local.toml.example``). The framework ships the script; the caps and
deadlines are personal.

Decision loop, each pass:
  0. If a ``stop_after`` deadline is set and reached, exit without restarting.
  1. Ask the probe for usage → RUN / WAIT / STOP_WEEKLY.
  2. STOP_WEEKLY → weekly ceiling hit; exit.
     WAIT <secs> → 5-hour window exhausted; sleep until it resets.
     RUN         → run the command, then re-check after ``interval``.
     no reading  → probe returned None (``usage_probe="none"``, no token, or a
                   fetch error); run the command once on the time cadence anyway
                   (for token-based probes this also re-auths for next pass).
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

DEFAULTS: Dict[str, object] = {
    "max_weekly_pct": 95.0,
    "daily_reserve_pct": 10.0,
    "max_session_pct": 98.0,
    "buffer_seconds": 30,
    "interval": 300,
    "wait_fallback": 900,
    "stop_after": "",
    "usage_probe": "none",    # "none" -> time cadence; adapters set e.g. "anthropic-oauth"
    "credentials_path": "",   # consumed by a token-based probe (empty -> its own default)
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
# usage probe (pluggable — the one core/adapter seam)
# --------------------------------------------------------------------------- #
# The engine defines the slot; an adapter fills it. When ``usage_probe`` is not
# "none", the engine imports the ``usage_probe.py`` module sitting next to this
# file and calls its ``get_usage(cfg) -> dict | None``. That indirection is what
# keeps the engine provider-neutral: it names a file, never a provider.
UsageProbe = Callable[[], Optional[Dict[str, object]]]


def _import_probe_module():
    """Import the adapter's ``usage_probe.py`` sibling, or return None if absent."""
    path = Path(__file__).resolve().parent / "usage_probe.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("aide_usage_probe", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_probe(cfg: Dict[str, object]) -> UsageProbe:
    """Resolve ``[loop] usage_probe`` to a zero-arg ``() -> dict | None`` callable.

    ``"none"`` (or unset) → a probe that always returns None, so the loop relaunches
    on the plain time cadence. Any other value selects the adapter-supplied
    ``usage_probe.py`` sibling module; if that module is missing or lacks
    ``get_usage``, the loop logs once and degrades to the same time cadence rather
    than crashing.
    """
    probe_id = str(cfg.get("usage_probe") or "none").strip().lower()
    if probe_id in ("", "none"):
        return lambda: None
    module = _import_probe_module()
    if module is None or not hasattr(module, "get_usage"):
        _log(f"usage_probe={probe_id!r} but no usage_probe.py with get_usage() "
             f"found next to loop.py — running on time cadence.")
        return lambda: None
    return lambda: module.get_usage(cfg)


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
    probe = load_probe(cfg)
    while True:
        now = _dt.datetime.now(_dt.timezone.utc)
        if _past_deadline(cfg, now):
            _log(f"Reached stop_after deadline ({cfg.get('stop_after')}). Not restarting.")
            return 0

        usage: Optional[Dict[str, object]] = None
        try:
            usage = probe()
        except Exception as exc:  # noqa: BLE001 - a broken probe must not wedge the loop
            _log(f"Usage probe raised ({exc}). Running command on time cadence…")
        if usage is None:
            _log("No usage reading (probe none/unavailable). Running command on time cadence…")
            subprocess.run(command)
            time.sleep(interval)
            continue
        try:
            action, arg, five, seven = decide_action(usage, cfg, now)
        except (ValueError, KeyError) as exc:
            _log(f"Could not interpret usage ({exc}). Running command on time cadence…")
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
        probe = load_probe(cfg)
        try:
            usage = probe()
        except Exception as exc:  # noqa: BLE001 - report, don't crash the diagnostic
            print(f"ERR {exc}")
            return 0
        if usage is None:
            print("ERR no-usage")
            return 0
        action, arg, five, seven = decide_action(usage, cfg)
        print(action, arg if arg is not None else "", round(five), round(seven))
        return 0
    return run_forever(cfg)


if __name__ == "__main__":
    sys.exit(main())
