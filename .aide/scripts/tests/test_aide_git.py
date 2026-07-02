"""Tests for the aide CLI git layer (claim, merge, env) — see aide.py.

The git-touching tests build throwaway repositories under ``tmp_path`` (a bare
repo stands in for ``origin`` where a remote is needed), so nothing touches the
real project or network.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_git", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"

[python]
venv = ".venv"
import_check = "demo_pkg"

[git]
mode = "{mode}"
main_branch = "main"
branch_prefix = "aide/"
"""

PROGRESS = """\
# Demo — Progress

## Stage summary

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 1 | Rules | G1 | 🚧 |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Rules | Stage 1 | 🚧 |

## Stage 1 — Rules — 🚧

**Deliverables.**
- ✅ Core. *(Item 026)*
- 📋 Bounds. *(Item 027)*
- 📋 Coverage. *(Item 028)*

**Acceptance.**
- [ ] Rules fire.
"""

QUEUE = """\
# Demo — Work Queue 003

> **Status:** Live · **Created:** 2026-07-01

### Item 026: Rule engine core
Core.

### Item 027: Bounds rules
Bounds.

### Item 028: Coverage rules
Coverage.
"""


def _run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _init_repo(path: Path, mode: str = "local") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "Tester"], path)
    (path / "aide.toml").write_text(AIDE_TOML.format(mode=mode), encoding="utf-8")
    d = path / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (d / "items").mkdir(parents=True)
    (d / "progress.md").write_text(PROGRESS, encoding="utf-8")
    (d / "queue" / "queue-003.md").write_text(QUEUE, encoding="utf-8")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)
    return path


def _current_branch(path: Path) -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).stdout.strip()


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_slug():
    assert aide._slug("Level-aware min/max bounds rules (volume)") == "level-aware-min-max-bounds"
    assert aide._slug("") == "item"


def test_queue_titles():
    titles = aide._queue_titles(QUEUE)
    assert titles[27] == "Bounds rules"


def test_venv_python_path(tmp_path: Path):
    cfg = aide.DEFAULT_CONFIG
    p = aide.venv_python(tmp_path, cfg)
    if os.name == "nt":
        assert p.name == "python.exe" and p.parent.name == "Scripts"
    else:
        assert p.name == "python" and p.parent.name == "bin"


def test_env_status_missing(tmp_path: Path):
    (tmp_path / "aide.toml").write_text(AIDE_TOML.format(mode="local"), encoding="utf-8")
    cfg = aide.load_config(tmp_path)
    assert aide.env_status(tmp_path, cfg) == "missing"


def test_pick_item_skips_done_and_claimed(tmp_path: Path):
    root = _init_repo(tmp_path / "r")
    cfg = aide.load_config(root)
    # 026 is done -> skip; 027 claimed -> skip; expect 028.
    pick = aide._pick_item(root, cfg, QUEUE, claim_branches=["aide/027-bounds"])
    assert pick is not None and pick[0] == 28


def test_pick_item_respects_dependency(tmp_path: Path):
    root = _init_repo(tmp_path / "r")
    # Give item 027 a spec that depends on 028 (still planned) -> 027 blocked, pick 028.
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\n- Item 028 provides X.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    pick = aide._pick_item(root, cfg, QUEUE, claim_branches=[])
    assert pick is not None and pick[0] == 28


# --------------------------------------------------------------------------- #
# claim
# --------------------------------------------------------------------------- #
def test_claim_local_creates_branch_no_push(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "claim"])
    assert rc == 0
    assert _current_branch(root) == "aide/027-bounds-rules"


def test_claim_dry_run_does_not_switch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "claim", "--dry-run"])
    assert rc == 0
    assert _current_branch(root) == "main"


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #
def _make_item_branch(root: Path, branch: str, filename: str) -> None:
    _run(["git", "switch", "-c", branch], root)
    (root / filename).write_text("work\n", encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-m", f"work on {branch}"], root)
    _run(["git", "switch", "main"], root)


def test_merge_local_merges_to_main(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    rc = aide.main(["--repo", str(root), "merge", "27", "--no-test"])
    assert rc == 0
    assert _current_branch(root) == "main"
    assert (root / "feature.txt").is_file()  # branch content is on main


def test_merge_pr_mode_pushes_and_stops(tmp_path: Path):
    # Bare remote so the push has somewhere to go; pr mode must NOT merge.
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="pr")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    rc = aide.main(["--repo", str(root), "merge", "27", "aide/027-bounds-rules", "--no-test"])
    assert rc == 0
    # pr mode does not merge: feature file absent on main.
    assert not (root / "feature.txt").is_file()
    # …but the branch was pushed to origin.
    refs = _run(["git", "ls-remote", "--heads", str(remote)], root).stdout
    assert "aide/027-bounds-rules" in refs


def test_merge_auto_merge_pushes_and_deletes_branch(tmp_path: Path):
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="auto-merge")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    _run(["git", "push", "-u", "origin", "aide/027-bounds-rules"], root)
    rc = aide.main(["--repo", str(root), "merge", "27", "--no-test"])
    assert rc == 0
    assert (root / "feature.txt").is_file()  # merged to main
    # Local claim branch deleted.
    branches = _run(["git", "branch"], root).stdout
    assert "aide/027-bounds-rules" not in branches
    # Remote claim branch deleted.
    refs = _run(["git", "ls-remote", "--heads", str(remote)], root).stdout
    assert "aide/027-bounds-rules" not in refs


def test_merge_missing_branch_errors(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "merge", "99", "--no-test"])
    assert rc == 1


def _mkbare(path: Path) -> Path:
    subprocess.run(["git", "init", "--bare", "-b", "main", str(path)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return path
