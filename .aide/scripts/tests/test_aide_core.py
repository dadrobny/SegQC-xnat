"""Tests for the aide CLI core (check, progress set, queue tidy) — see aide.py.

Style mirrors tests/test_aide_status_report.py: load the script by path (it lives
under .aide/scripts, not on the package path) and exercise its pure functions,
plus a couple of end-to-end CLI invocations over a temp docs tree.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
source_dir = "src/demo"
docs_dir = "docs/aide"

[git]
mode = "pr"
branch_prefix = "aide/"

[loop]
queue_cap = 8
clarify = "interactive"
"""

PROGRESS = """\
# Demo — Progress

## Stage summary

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | Scaffolding | (foundation) | ✅ |
| 1 | Rule Engine | G2 | 🚧 |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Setup | Stage 0 | ✅ |
| G2 Rules | Stage 1 | 🚧 |

## Stage 0 — Scaffolding — ✅

**Deliverables.**
- ✅ Package. *(Item 001)*

**Acceptance.**
- [x] It builds.

## Stage 1 — Rule Engine — 🚧

**Deliverables.**
- ✅ Core. *(Item 002)*
- 📋 Bounds. *(Item 003)*

**Acceptance.**
- [ ] Rules fire.
- [ ] Config-driven.
"""

QUEUE_LIVE = """\
# Demo — Work Queue 002

> **Status:** Live · **Created:** 2026-07-01

### Item 002: Core
Do the core.

### Item 003: Bounds
Do bounds.
"""

QUEUE_OLD = """\
# Demo — Work Queue 001

> **Status:** ✅ Completed — superseded by queue-002 (2026-06-01).

### Item 001: Package
Scaffold.
"""


# --------------------------------------------------------------------------- #
# config / toml
# --------------------------------------------------------------------------- #
def test_parse_toml_scalars():
    parsed = aide._parse_toml(AIDE_TOML)
    assert parsed["project"]["name"] == "Demo"
    assert parsed["git"]["mode"] == "pr"
    assert parsed["loop"]["queue_cap"] == 8
    assert parsed["loop"]["clarify"] == "interactive"


def test_load_config_merges_over_defaults(tmp_path: Path):
    (tmp_path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    cfg = aide.load_config(tmp_path)
    assert cfg["project"]["name"] == "Demo"
    assert cfg["git"]["mode"] == "pr"
    # Unspecified keys fall back to defaults.
    assert cfg["git"]["main_branch"] == "main"
    assert cfg["python"]["venv"] == ".venv"


def test_load_config_missing_file_is_defaults(tmp_path: Path):
    cfg = aide.load_config(tmp_path)
    assert cfg["git"]["mode"] == "auto-merge"


def test_find_repo_root_walks_up(tmp_path: Path):
    (tmp_path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert aide.find_repo_root(nested) == tmp_path.resolve()


# --------------------------------------------------------------------------- #
# progress parsing / rollup
# --------------------------------------------------------------------------- #
def test_rollup_status():
    assert aide.rollup_status(["complete", "complete"]) == "complete"
    assert aide.rollup_status(["complete", "planned"]) == "in-progress"
    assert aide.rollup_status(["planned", "planned"]) == "planned"
    assert aide.rollup_status(["complete", "deferred"]) == "complete"
    assert aide.rollup_status([]) is None


def test_stage_sections_bounds():
    lines = PROGRESS.splitlines()
    secs = aide.stage_sections(lines)
    nums = [n for _, _, n in secs]
    assert nums == ["0", "1"]


# --------------------------------------------------------------------------- #
# set_item_status
# --------------------------------------------------------------------------- #
def test_set_item_in_progress_flips_only_bullet():
    out = aide.set_item_status(PROGRESS, 3, "in-progress")
    assert "- 🚧 Bounds. *(Item 003)*" in out
    # Stage still in progress, acceptance untouched.
    assert "## Stage 1 — Rule Engine — 🚧" in out
    assert "- [ ] Rules fire." in out


def test_set_item_done_completes_stage_and_ticks_acceptance():
    out = aide.set_item_status(PROGRESS, 3, "complete")
    assert "- ✅ Bounds. *(Item 003)*" in out
    assert "- [x] Rules fire." in out
    assert "- [x] Config-driven." in out
    assert "## Stage 1 — Rule Engine — ✅" in out
    assert "| 1 | Rule Engine | G2 | ✅ |" in out
    assert "| G2 Rules | Stage 1 | ✅ |" in out


def test_set_item_never_downgrades():
    out = aide.set_item_status(PROGRESS, 2, "in-progress")  # already complete
    assert "- ✅ Core. *(Item 002)*" in out


def test_set_item_wrapped_continuation_ref():
    text = (
        "## Stage 2 — X — 🚧\n"
        "**Deliverables.**\n"
        "- 📋 A long deliverable that wraps onto a\n"
        "  second line. *(Item 042)*\n"
    )
    out = aide.set_item_status(text, 42, "in-progress")
    assert "- 🚧 A long deliverable that wraps onto a" in out


def test_set_item_unknown_number_no_change():
    out = aide.set_item_status(PROGRESS, 999, "complete")
    assert out == PROGRESS


# --------------------------------------------------------------------------- #
# queue helpers
# --------------------------------------------------------------------------- #
def test_is_live_queue():
    assert aide.is_live_queue(QUEUE_LIVE)
    assert not aide.is_live_queue(QUEUE_OLD)


def test_queue_item_numbers():
    assert aide.queue_item_numbers(QUEUE_LIVE) == [2, 3]


def test_tidy_queue_text_rewrites_status():
    out = aide.tidy_queue_text(QUEUE_LIVE, superseded_by=3, date="2026-07-02")
    assert "> **Status:** ✅ Completed — superseded by queue-003 (2026-07-02)." in out
    assert not aide.is_live_queue(out)
    # Items are untouched.
    assert "### Item 002: Core" in out


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def _docs(tmp_path: Path, progress=PROGRESS, live=QUEUE_LIVE, old=QUEUE_OLD) -> Path:
    (tmp_path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    d = tmp_path / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (d / "items").mkdir(parents=True)
    (d / "progress.md").write_text(progress, encoding="utf-8")
    (d / "queue" / "queue-001.md").write_text(old, encoding="utf-8")
    (d / "queue" / "queue-002.md").write_text(live, encoding="utf-8")
    return tmp_path


def test_check_passes_on_valid_docs(tmp_path: Path):
    root = _docs(tmp_path)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert errors == [], errors


def test_check_flags_missing_stage_table(tmp_path: Path):
    root = _docs(tmp_path, progress="# Demo\n\nNo tables, no stages.\n")
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("Stage summary table" in e for e in errors)


def test_check_flags_summary_complete_but_deliverable_not(tmp_path: Path):
    bad = PROGRESS.replace("| 1 | Rule Engine | G2 | 🚧 |", "| 1 | Rule Engine | G2 | ✅ |")
    bad = bad.replace("## Stage 1 — Rule Engine — 🚧", "## Stage 1 — Rule Engine — ✅")
    root = _docs(tmp_path, progress=bad)
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("marked ✅ but has non-complete" in e for e in errors)


def test_check_flags_two_live_queues(tmp_path: Path):
    root = _docs(tmp_path, old=QUEUE_LIVE.replace("Queue 002", "Queue 001"))
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("more than one Live queue" in e for e in errors)


def test_check_flags_duplicate_item_across_queues(tmp_path: Path):
    dup = QUEUE_OLD.replace("### Item 001: Package", "### Item 002: Package")
    root = _docs(tmp_path, old=dup)
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("appears in both" in e for e in errors)


def test_check_warns_stale_claim_branch(tmp_path: Path):
    root = _docs(tmp_path)
    cfg = aide.load_config(root)
    # Item 002 is complete; a claim branch for it is stale.
    _, warnings = aide.run_checks(root, cfg, branches=["aide/002-core"])
    assert any("stale claim branch" in w for w in warnings)


# --------------------------------------------------------------------------- #
# CLI end-to-end
# --------------------------------------------------------------------------- #
def test_cli_check_ok(tmp_path: Path, capsys):
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "check"])
    assert rc == 0


def test_cli_progress_set_edits_file(tmp_path: Path):
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "progress", "set", "3", "done", "--no-commit"])
    assert rc == 0
    text = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    assert "- ✅ Bounds. *(Item 003)*" in text
    assert "- [x] Rules fire." in text


def test_cli_queue_tidy_edits_file(tmp_path: Path):
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "queue", "tidy", "1", "--date", "2026-07-02"])
    assert rc == 0
    text = (root / "docs" / "aide" / "queue" / "queue-001.md").read_text(encoding="utf-8")
    assert "Completed — superseded by queue-002 (2026-07-02)" in text
