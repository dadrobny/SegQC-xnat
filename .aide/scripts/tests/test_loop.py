"""Tests for the loop supervisor's pure decision logic (.aide/loop/loop.py).

Only the deterministic parts are unit-tested — the network fetch and the sleeping
supervisor loop are I/O and out of scope here.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[2] / "loop" / "loop.py"
_spec = importlib.util.spec_from_file_location("aide_loop", _MODULE_PATH)
loop = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = loop
_spec.loader.exec_module(loop)  # type: ignore[union-attr]

NOW = _dt.datetime(2026, 7, 2, 12, 0, tzinfo=_dt.timezone.utc)


def _usage(five, seven, five_reset="2026-07-02T15:00:00Z", seven_reset="2026-07-05T12:00:00Z"):
    return {
        "five_hour": {"utilization": five, "resets_at": five_reset},
        "seven_day": {"utilization": seven, "resets_at": seven_reset},
    }


def test_run_when_under_all_limits():
    cfg = dict(loop.DEFAULTS)
    action, arg, five, seven = loop.decide_action(_usage(40, 50), cfg, NOW)
    assert action == "RUN"
    assert (five, seven) == (40, 50)


def test_stop_weekly_on_fixed_cap():
    cfg = dict(loop.DEFAULTS, daily_reserve_pct=0, max_weekly_pct=95)
    action, arg, _, _ = loop.decide_action(_usage(10, 96), cfg, NOW)
    assert action == "STOP_WEEKLY"
    assert arg == 95


def test_stop_weekly_on_daily_reserve():
    # 3 days left, reserve 10%/day -> ceiling 70; weekly 75 exceeds it.
    cfg = dict(loop.DEFAULTS, max_weekly_pct=0, daily_reserve_pct=10)
    action, arg, _, _ = loop.decide_action(_usage(10, 75), cfg, NOW)
    assert action == "STOP_WEEKLY"
    assert arg == 70


def test_wait_when_session_exhausted():
    cfg = dict(loop.DEFAULTS, max_session_pct=98, buffer_seconds=30)
    action, arg, _, _ = loop.decide_action(_usage(99, 20), cfg, NOW)
    assert action == "WAIT"
    # 3 hours to reset + 30s buffer.
    assert arg == 3 * 3600 + 30


def test_smaller_ceiling_wins():
    # Fixed cap 95, daily-reserve cap 70 -> 70 wins; weekly 72 stops.
    cfg = dict(loop.DEFAULTS, max_weekly_pct=95, daily_reserve_pct=10)
    action, arg, _, _ = loop.decide_action(_usage(10, 72), cfg, NOW)
    assert action == "STOP_WEEKLY"
    assert arg == 70


def test_load_config_uses_defaults_when_missing(tmp_path: Path):
    cfg = loop.load_loop_config(tmp_path / "nope.toml")
    assert cfg["max_weekly_pct"] == 95.0
    assert cfg["interval"] == 300


def test_parse_toml_reads_loop_table():
    cfg = loop._parse_toml('[loop]\nmax_weekly_pct = 80\ncommand = "claude \\"/x\\""\n')
    assert cfg["max_weekly_pct"] == 80


def test_command_default_is_plain_roadmap():
    assert loop._command({}) == ["claude", "/aide-run-roadmap"]


def test_past_deadline():
    cfg = {"stop_after": "2026-07-02T09:00:00"}
    assert loop._past_deadline(cfg, NOW) is True
    cfg2 = {"stop_after": "2026-07-02T15:00:00"}
    assert loop._past_deadline(cfg2, NOW) is False
    assert loop._past_deadline({"stop_after": ""}, NOW) is False
