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

import pytest

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
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding="utf-8")


def _show_utf8(cwd: Path, rev_path: str) -> str:
    """`git show <rev>:<path>`, decoded as UTF-8 **strictly**.

    The documents this project reads are UTF-8 by definition (conventions.md
    §1), so anything reading one out of git says so rather than inheriting the
    platform's guess. Left decoding from bytes even though `_run` now names the
    codec itself: this one wants the *strict* decoder, so a byte that is not
    UTF-8 raises here instead of arriving as a replacement character that no
    status icon matches. That is the recorded §6 shape — the locale codec
    mangled the icons into characters `_parse_item_status` could not match,
    green on Linux and red only on the platform no local run sees.
    """
    out = subprocess.run(["git", "show", rev_path], cwd=str(cwd), check=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    return out.decode("utf-8")


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


def test_env_profile_satisfied_and_not(tmp_path: Path, capsys):
    (tmp_path / "aide.toml").write_text(
        AIDE_TOML.format(mode="local")
        + '\n[validation]\nyes = "1 + 1 == 2"\nno = "False"\n',
        encoding="utf-8",
    )
    assert aide.main(["--repo", str(tmp_path), "env", "--profile", "yes"]) == 0
    assert aide.main(["--repo", str(tmp_path), "env", "--profile", "no"]) == 1
    assert aide.main(["--repo", str(tmp_path), "env", "--profile", "nope"]) == 2
    err = capsys.readouterr().err
    assert "unknown profile 'nope'" in err


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


def test_item_dependencies_expands_every_number_in_a_multi_item_list(tmp_path: Path):
    # Regression: a naive first-number-only regex left every item after the
    # first in "Items 026, 027, 028" unrecognised as a blocker.
    # _item_dependencies itself is status-agnostic — it reports every number
    # the section names; _pick_item is what discards already-✅ dependencies
    # (see test_pick_item_not_blocked_once_every_multi_item_dependency_is_done
    # below for that half of the behaviour).
    root = _init_repo(tmp_path / "r")
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\n"
        "- Items 026, 028 — both must land first.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    assert aide._item_dependencies(root, cfg, 27) == [26, 28]


def test_pick_item_not_blocked_once_every_multi_item_dependency_is_done(tmp_path: Path):
    # The practical regression: with 026 already ✅ (per PROGRESS) and 027
    # depending on "Items 026, 028", 027 must stay blocked while 028 is still
    # planned — a naive first-number-only parse would have reported 027 as
    # unblocked (it only ever saw 026, which is done) the moment 026 landed.
    root = _init_repo(tmp_path / "r")
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\n"
        "- Items 026, 028 — both must land first.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    pick = aide._pick_item(root, cfg, QUEUE, claim_branches=[])
    assert pick is not None and pick[0] == 28  # 027 is still blocked by open 028


def test_item_dependencies_is_case_insensitive(tmp_path: Path):
    root = _init_repo(tmp_path / "r")
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\n- lowercase item 028 still blocks.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    assert aide._item_dependencies(root, cfg, 27) == [28]


def test_item_dependencies_ignores_downstream_forward_reference(tmp_path: Path):
    # Regression: "**Downstream:** item 028 depends on this item" was
    # previously misread as item 027 depending ON 028 (backwards) — the exact
    # bug that let `aide claim` skip an unblocked item in favour of a wrong one.
    root = _init_repo(tmp_path / "r")
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\n"
        "- Item 026 provides X.\n\n"
        "**Downstream:** item 028 depends on this item's output.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    assert aide._item_dependencies(root, cfg, 27) == [26]


def test_pick_item_not_blocked_by_a_downstream_forward_reference(tmp_path: Path):
    root = _init_repo(tmp_path / "r")
    # 027 mentions 028 only as a downstream forward reference -> 027 must be
    # pickable even though 028 is still planned.
    (root / "docs" / "aide" / "items" / "027-bounds.md").write_text(
        "# Item 027 — Bounds\n\n## Dependencies\nNone.\n\n"
        "**Downstream:** item 028 depends on this item's output.\n\n## End\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    pick = aide._pick_item(root, cfg, QUEUE, claim_branches=[])
    assert pick is not None and pick[0] == 27


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


# --------------------------------------------------------------------------- #
# claim scope (WI-2: derived queue state, opt-in cross-queue claiming)
# --------------------------------------------------------------------------- #
QUEUE_NEXT = """\
# Demo — Work Queue 004

> **Created:** 2026-07-02

### Item 029: Extra rules
Extra.
"""


def _add_next_queue_and_claim_all(root: Path) -> None:
    (root / "docs" / "aide" / "queue" / "queue-004.md").write_text(QUEUE_NEXT, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-m", "queue 004"], root)
    # Claim branches exist for every open item of queue-003.
    _run(["git", "branch", "aide/027-bounds-rules"], root)
    _run(["git", "branch", "aide/028-coverage-rules"], root)


def test_claim_default_scope_stops_at_live_queue(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    _add_next_queue_and_claim_all(root)
    rc = aide.main(["--repo", str(root), "claim", "--dry-run"])
    assert rc == 0
    assert "none left" in capsys.readouterr().out


def test_claim_all_open_scope_spans_queues(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    _add_next_queue_and_claim_all(root)
    toml = (root / "aide.toml").read_text(encoding="utf-8")
    (root / "aide.toml").write_text(
        toml + '\n[loop]\nclaim_scope = "all-open"\n', encoding="utf-8")
    rc = aide.main(["--repo", str(root), "claim", "--dry-run"])
    assert rc == 0
    assert "would claim item 029" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# sync (WI-3: deterministic preflight)
# --------------------------------------------------------------------------- #
def test_sync_ok_on_clean_tree(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "sync"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_sync_fails_on_dirty_tree(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    (root / "uncommitted.txt").write_text("wip\n", encoding="utf-8")
    rc = aide.main(["--repo", str(root), "sync"])
    assert rc == 1
    assert "not clean" in capsys.readouterr().err


def test_sync_item_switches_to_claim_branch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")  # ends on main
    rc = aide.main(["--repo", str(root), "sync", "--item", "27"])
    assert rc == 0
    assert _current_branch(root) == "aide/027-bounds-rules"


def test_sync_item_without_claim_branch_errors(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "sync", "--item", "28"])
    assert rc == 1
    assert "no claim branch" in capsys.readouterr().err


def test_sync_fast_forwards_main(tmp_path: Path):
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="auto-merge")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    # A second clone advances origin/main past our local main.
    other = tmp_path / "other"
    _run(["git", "clone", str(remote), str(other)], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], other)
    _run(["git", "config", "user.name", "Tester"], other)
    (other / "new.txt").write_text("x\n", encoding="utf-8")
    _run(["git", "add", "-A"], other)
    _run(["git", "commit", "-m", "remote work"], other)
    _run(["git", "push"], other)
    rc = aide.main(["--repo", str(root), "sync"])
    assert rc == 0
    assert (root / "new.txt").is_file()  # local main caught up


# --------------------------------------------------------------------------- #
# gc (WI-3: claim-branch garbage collection)
# --------------------------------------------------------------------------- #
def _squash_merge(root: Path, branch: str, message: str) -> None:
    """Land *branch* on main the way GitHub's "Squash and merge" does.

    The shape `gc` reaches for `git branch -D` to cope with: the content is on
    main, but the branch tip is no ancestor of it, so `git branch --merged`
    cannot see it.
    """
    _run(["git", "switch", "main"], root)
    _run(["git", "merge", "--squash", branch], root)
    _run(["git", "commit", "-m", message], root)


def test_gc_dry_run_lists_a_landed_stale_branch(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    # Item 026 is ✅ in progress.md; its work landed, so the branch is stale.
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    rc = aide.main(["--repo", str(root), "gc"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would delete aide/026-rule-engine-core" in out
    assert "dry run" in out
    branches = _run(["git", "branch"], root).stdout
    assert "aide/026-rule-engine-core" in branches  # nothing deleted


def test_gc_yes_deletes_local_and_remote(tmp_path: Path):
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="auto-merge")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _run(["git", "push", "-u", "origin", "aide/026-rule-engine-core"], root)
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    _run(["git", "push", "origin", "main"], root)
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    assert rc == 0
    branches = _run(["git", "branch"], root).stdout
    assert "aide/026-rule-engine-core" not in branches
    refs = _run(["git", "ls-remote", "--heads", str(remote)], root).stdout
    assert "aide/026-rule-engine-core" not in refs


# --------------------------------------------------------------------------- #
# gc — the ✅ ground asks git whether the work actually landed
# --------------------------------------------------------------------------- #
def test_gc_refuses_a_tick_whose_branch_has_unlanded_content(tmp_path: Path, capsys):
    """The defect: `progress.md` said ✅, git was never asked, and `-D` plus a
    remote delete discarded a commit that had never merged."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "aide/026-rule-engine-core" in _run(["git", "branch"], root).stdout
    assert "skipping aide/026-rule-engine-core" in out
    assert "main" in out  # the skip names the base it was measured against


def test_gc_abandon_deletes_an_unlanded_tick_on_purpose(tmp_path: Path):
    """Abandoning a claim is a real part of the lifecycle (conventions §2) — it
    just has to be asked for, not inferred from a document."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    rc = aide.main(["--repo", str(root), "gc", "--abandon", "--yes"])
    assert rc == 0
    assert "aide/026-rule-engine-core" not in _run(["git", "branch"], root).stdout


def test_gc_deletes_a_single_commit_squash_merge(tmp_path: Path):
    """No regression in the case `-D` exists to serve."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    assert aide.main(["--repo", str(root), "gc", "--yes"]) == 0
    assert "aide/026-rule-engine-core" not in _run(["git", "branch"], root).stdout


def test_gc_deletes_a_multi_commit_squash_merge(tmp_path: Path):
    """The shape `git cherry` gets wrong — it reports a false alarm — and the
    reason `merge-tree --write-tree` is the oracle rather than `cherry`."""
    root = _init_repo(tmp_path / "r", mode="local")
    _run(["git", "switch", "-c", "aide/026-rule-engine-core"], root)
    for n in ("one", "two"):
        (root / f"{n}.txt").write_text(f"{n}\n", encoding="utf-8")
        _run(["git", "add", "-A"], root)
        _run(["git", "commit", "-m", f"part {n}"], root)
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    assert aide.main(["--repo", str(root), "gc", "--yes"]) == 0
    assert "aide/026-rule-engine-core" not in _run(["git", "branch"], root).stdout


def test_gc_still_deletes_after_the_base_advances_with_unrelated_work(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    (root / "unrelated.txt").write_text("later\n", encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-m", "unrelated work"], root)
    assert aide.main(["--repo", str(root), "gc", "--yes"]) == 0
    assert "aide/026-rule-engine-core" not in _run(["git", "branch"], root).stdout


def test_gc_refuses_the_tick_ground_on_git_too_old(tmp_path: Path, capsys, monkeypatch):
    """Old git becomes MORE conservative, never less: no second oracle, and
    nobody's `gc` stops working — it just declines this ground and says why."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    monkeypatch.setattr(aide, "_git_version", lambda _root: (2, 34))
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "aide/026-rule-engine-core" in _run(["git", "branch"], root).stdout
    assert "2.38" in out


# --------------------------------------------------------------------------- #
# gc — the preview is the set --yes acts on
# --------------------------------------------------------------------------- #
def _gc_lines(capsys) -> set:
    """Branch names the run reported as deletable, from either path."""
    out = capsys.readouterr().out
    prefixes = ("would delete ", "deleted ")
    return {line[len(pre):].split()[0]
            for line in out.splitlines() for pre in prefixes
            if line.startswith(pre)}


def test_gc_preview_and_yes_report_the_same_set(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")  # 📋, kept
    capsys.readouterr()
    aide.main(["--repo", str(root), "gc"])
    previewed = _gc_lines(capsys)
    aide.main(["--repo", str(root), "gc", "--yes"])
    assert _gc_lines(capsys) == previewed


def test_gc_preview_does_not_promise_to_delete_the_checked_out_branch(
        tmp_path: Path, capsys):
    """The preview used to list a branch `--yes` then silently skipped."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    _run(["git", "switch", "aide/026-rule-engine-core"], root)
    capsys.readouterr()
    aide.main(["--repo", str(root), "gc"])
    previewed = _gc_lines(capsys)
    assert previewed == set()
    aide.main(["--repo", str(root), "gc", "--yes"])
    assert _gc_lines(capsys) == previewed
    assert "aide/026-rule-engine-core" in _run(["git", "branch"], root).stdout


def test_gc_protects_a_branch_at_a_detached_head(tmp_path: Path, capsys):
    """`rev-parse --abbrev-ref HEAD` returns the literal 'HEAD' when detached,
    and no branch equals that — so the guard protected nothing."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    _run(["git", "checkout", "--detach", "aide/026-rule-engine-core"], root)
    capsys.readouterr()
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    assert rc == 0
    assert _gc_lines(capsys) == set()
    assert "aide/026-rule-engine-core" in _run(["git", "branch"], root).stdout


def test_gc_merged_now_sees_a_squash_merge(tmp_path: Path):
    """`--merged` is built on ancestry and missed every squash merge; the same
    oracle that guards the ✅ ground closes that too."""
    root = _init_repo(tmp_path / "r", mode="local")
    # Item 027 is 📋, so only the --merged ground can collect this.
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    _squash_merge(root, "aide/027-bounds-rules", "squash 027")
    assert aide.main(["--repo", str(root), "gc", "--merged", "--yes"]) == 0
    assert "aide/027-bounds-rules" not in _run(["git", "branch"], root).stdout


def test_gc_keeps_active_item_branch(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    # Item 027 is 📋 (not complete) — its claim branch must survive gc.
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    assert rc == 0
    branches = _run(["git", "branch"], root).stdout
    assert "aide/027-bounds-rules" in branches


def test_gc_merged_deletes_merged_branch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    # Branch for 📋 item merged into main (e.g. landed by hand): --merged collects it.
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    _run(["git", "merge", "--no-edit", "aide/027-bounds-rules"], root)
    rc = aide.main(["--repo", str(root), "gc", "--merged", "--yes"])
    assert rc == 0
    branches = _run(["git", "branch"], root).stdout
    assert "aide/027-bounds-rules" not in branches


# --------------------------------------------------------------------------- #
# branch parsing — queue numbers and item numbers share one namespace
# --------------------------------------------------------------------------- #
def test_branch_item_number_reads_a_claim_branch():
    assert aide._branch_item_number("aide/026-rule-engine-core", "aide/") == 26
    assert aide._branch_item_number("aide/007-x", "aide/") == 7
    assert aide._branch_item_number("aide/026", "aide/") == 26


def test_branch_item_number_rejects_a_queue_branch():
    """The defect this anchoring exists to prevent.

    `aide/queue-016` used to resolve to item 016 — an unrelated, long-finished
    work item — because the fallback searched anywhere in the branch name for a
    digit run. `gc` deletes a branch whose item is ✅ using `git branch -D` plus
    a remote delete, independently of `--merged`, so that misread could destroy
    an in-flight queue branch carrying unreviewed specs.
    """
    assert aide._branch_item_number("aide/queue-016", "aide/") is None
    assert aide._branch_item_number("aide/specs-queue-015", "aide/") is None
    assert aide._is_queue_branch("aide/queue-016", "aide/")
    assert aide._is_queue_branch("aide/specs-queue-015", "aide/")


def test_branch_item_number_rejects_an_unnumbered_branch():
    assert aide._branch_item_number("aide/fix-the-thing", "aide/") is None
    assert not aide._is_queue_branch("aide/fix-the-thing", "aide/")


def test_branch_item_number_honours_a_custom_prefix():
    assert aide._branch_item_number("wip/031-x", "wip/") == 31
    assert aide._branch_item_number("aide/031-x", "wip/") is None


# --------------------------------------------------------------------------- #
# branch construction — every name the engine produces, read back by the
# recogniser that must later parse it
# --------------------------------------------------------------------------- #
#: Prefixes chosen to break a careless implementation: the default; one with no
#: separator; one containing a digit (a prefix-swallowing `\d+` reads `2` as the
#: number); and one whose text ends in the queue token itself.
_PREFIXES = ["aide/", "wip/", "v2/", "aide", "team/queue-"]


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("number", [1, 16, 123, 1234])
def test_queue_branch_name_round_trips_through_its_recogniser(prefix, number):
    """The test #72 exists to make possible.

    Until 1.20.0 `<prefix>queue-NNN` had no constructor — an agent typed it out
    of a markdown file — so there was nothing to round-trip and the regex that
    parses it never saw a name until something had already gone wrong.
    """
    branch = aide.queue_branch_name(prefix, number)
    assert aide._is_queue_branch(branch, prefix)
    # And is never mistaken for the same-numbered item claim, which is the
    # misread that once let `gc` delete an in-flight queue branch.
    assert aide._branch_item_number(branch, prefix) is None


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("number", [1, 16, 123, 1234])
def test_specs_queue_branch_name_round_trips_through_its_recogniser(prefix, number):
    branch = aide.specs_queue_branch_name(prefix, number)
    assert aide._is_queue_branch(branch, prefix)
    assert aide._branch_item_number(branch, prefix) is None


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("number", [1, 16, 123, 1234])
def test_claim_branch_name_round_trips_through_its_recogniser(prefix, number):
    branch = aide.claim_branch_name(prefix, number, "Rule engine core")
    assert aide._branch_item_number(branch, prefix) == number
    assert not aide._is_queue_branch(branch, prefix)


def test_branch_constructors_produce_the_documented_shapes():
    """Pins the literal text, so a refactor of the token cannot quietly
    re-shape every branch name the framework tells a human to expect."""
    assert aide.queue_branch_name("aide/", 16) == "aide/queue-016"
    assert aide.specs_queue_branch_name("aide/", 15) == "aide/specs-queue-015"
    assert aide.claim_branch_name("aide/", 26, "Rule engine core") == \
        "aide/026-rule-engine-core"


def test_queue_branch_recogniser_still_accepts_unpadded_digits():
    """Constructors always pad; a human or an older run may not have."""
    assert aide._is_queue_branch("aide/queue-16", "aide/")
    assert aide._is_queue_branch("aide/specs-queue-5", "aide/")


def test_a_slugged_queue_branch_is_still_not_recognised():
    """#55 (queue slugs) is deferred and this records the state, not a wish.

    With one constructor, changing the shape becomes a one-place edit whose
    failure this suite catches — rather than a mis-targeted merge in a live run.
    """
    assert not aide._is_queue_branch("aide/queue-016-stage-27", "aide/")


# --------------------------------------------------------------------------- #
# aide queue start
# --------------------------------------------------------------------------- #
def test_queue_start_creates_and_records_its_base(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "queue", "start", "16"])
    assert rc == 0
    assert _current_branch(root) == "aide/queue-016"
    assert aide._recorded_branch_base(root, "aide/queue-016") == "main"


def test_queue_start_specs_creates_the_specs_branch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "queue", "start", "15", "--specs"])
    assert rc == 0
    assert _current_branch(root) == "aide/specs-queue-015"


def test_queue_start_dry_run_creates_nothing(tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "queue", "start", "16", "--dry-run"])
    assert rc == 0
    assert "aide/queue-016" in capsys.readouterr().out
    assert _current_branch(root) == "main"
    assert "aide/queue-016" not in _run(["git", "branch"], root).stdout


def test_queue_start_refuses_a_base_that_is_not_a_local_branch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "queue", "start", "16", "--base", "nope"])
    assert rc == 1
    assert _current_branch(root) == "main"


def test_queue_start_refuses_to_recreate_an_existing_branch(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    assert aide.main(["--repo", str(root), "queue", "start", "16"]) == 0
    _run(["git", "switch", "main"], root)
    assert aide.main(["--repo", str(root), "queue", "start", "16"]) == 1


def test_queue_start_branches_from_the_named_base_not_head(tmp_path: Path):
    """`switch -c` with no start point uses HEAD, which would let the branch's
    real origin disagree with the base it records."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/099-elsewhere", "stray.txt")
    _run(["git", "switch", "aide/099-elsewhere"], root)
    rc = aide.main(["--repo", str(root), "queue", "start", "16", "--base", "main"])
    assert rc == 0
    assert not (root / "stray.txt").is_file()


def test_a_claim_off_a_started_queue_branch_merges_back_into_it(tmp_path: Path):
    """The failure #72 measured: an unrecognised queue branch made `claim`
    fall back to `main_branch`, merging the item past the queue branch."""
    root = _init_repo(tmp_path / "r", mode="local")
    assert aide.main(["--repo", str(root), "queue", "start", "3"]) == 0
    assert aide.main(["--repo", str(root), "claim", "--queue", "3"]) == 0
    branch = _current_branch(root)
    assert aide._recorded_branch_base(root, branch) == "aide/queue-003"


def test_gc_never_deletes_a_queue_branch_for_a_same_numbered_item(tmp_path: Path, capsys):
    """Item 026 is ✅, but `aide/queue-026` is not item 026's claim branch."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/queue-026", "queue.txt")
    rc = aide.main(["--repo", str(root), "gc", "--yes"])
    assert rc == 0
    branches = _run(["git", "branch"], root).stdout
    assert "aide/queue-026" in branches
    assert "deleted" not in capsys.readouterr().out


def test_check_does_not_report_a_queue_branch_as_a_stale_claim(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=["aide/queue-026"])
    assert not any("stale claim" in w for w in warnings)
    assert not any("unrecognised" in w for w in warnings)


def test_check_reports_a_prefixed_branch_it_cannot_parse(tmp_path: Path):
    """Anchoring must not turn a real stale claim into a silent skip."""
    root = _init_repo(tmp_path / "r", mode="local")
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=["aide/rule-engine-core"])
    assert any("unrecognised branch aide/rule-engine-core" in w for w in warnings)


def test_unrecognised_branch_warning_names_the_remedy(tmp_path: Path):
    """A warning that explains the convention but not the fix sends the reader
    to raw git, which is what the CLI's own convention says to avoid."""
    root = _init_repo(tmp_path / "r", mode="local")
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=["aide/rule-engine-core"])
    warning = next(w for w in warnings if "unrecognised branch" in w)
    assert "rename" in warning
    assert "aide gc --merged" in warning


# --------------------------------------------------------------------------- #
# gc signposting — an empty result is about a ground and a scope, not the repo
# --------------------------------------------------------------------------- #
def test_gc_empty_default_points_at_merged_when_it_would_find_something(
        tmp_path: Path, capsys):
    """The item ground structurally cannot see a queue branch; --merged can.

    Reporting a bare "nothing to clean" while `aide gc --merged` would offer
    three branches is a true statement about the ground checked read as a false
    one about the repository.
    """
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/queue-026", "queue.txt")
    _run(["git", "merge", "--no-edit", "aide/queue-026"], root)
    rc = aide.main(["--repo", str(root), "gc"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "nothing to clean" in out
    assert "aide gc --merged" in out


def test_gc_empty_result_stays_terse_when_there_is_nothing_to_add(
        tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "gc"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "aide gc: nothing to clean"


def test_gc_states_its_scope_when_branches_sit_outside_the_prefix(
        tmp_path: Path, capsys):
    """gc only ever looks at branches under the prefix -- correctly, since it
    must not delete branches it does not own. The defect is that the
    restriction was silent, so "nothing to clean" read as "no cleanup exists"
    for a merged branch gc had never even considered."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "fix/33-signposting", "fix.txt")
    _run(["git", "merge", "--no-edit", "fix/33-signposting"], root)
    rc = aide.main(["--repo", str(root), "gc"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "nothing to clean" in out
    assert "1 local branch outside the 'aide/' scope was not considered" in out


def test_gc_does_not_probe_merged_when_the_flag_was_passed(tmp_path: Path, capsys):
    """With --merged already given, naming --merged again would be nonsense."""
    root = _init_repo(tmp_path / "r", mode="local")
    rc = aide.main(["--repo", str(root), "gc", "--merged"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "aide gc --merged" not in out


def _mkbare(path: Path) -> Path:
    subprocess.run(["git", "init", "--bare", "-b", "main", str(path)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return path


# --------------------------------------------------------------------------- #
# 🔍 In Review — ✅ means "merged", in every git.mode
# --------------------------------------------------------------------------- #
def test_in_review_rolls_a_stage_up_to_in_progress_not_complete():
    """The whole point: an open PR must not roll a stage up to "shipped"."""
    assert aide.rollup_status(["in-review"]) == "in-progress"
    assert aide.rollup_status(["complete", "in-review"]) == "in-progress"
    assert aide.rollup_status(["complete"]) == "complete"


def test_in_review_outranks_in_progress_and_is_outranked_by_complete():
    assert aide.RANK["in-progress"] < aide.RANK["in-review"] < aide.RANK["complete"]


def test_in_review_keeps_its_queue_open():
    """A queue is not finished with an item whose review has not happened."""
    text = "### Item 026 — x\n"
    assert aide.queue_is_open(text, {26: "in-review"})
    assert not aide.queue_is_open(text, {26: "complete"})


def test_merge_records_the_tick_itself_in_local_mode(tmp_path: Path):
    """✅ is set by the process that did the merge, so it cannot outrun it."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27", "in-review",
                      "--no-commit"]) == 0
    assert aide.main(["--repo", str(root), "merge", "27", "--no-test"]) == 0
    progress = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    assert "✅ Bounds rules" in progress or "27" in progress
    _, _, status = aide._parse_item_status(progress.splitlines())
    assert status[27] == "complete"


def test_pr_mode_merge_leaves_the_item_in_review(tmp_path: Path, capsys):
    """The designed state #71 names: pushed, awaiting a human — NOT ✅."""
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="pr")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27", "in-review",
                      "--no-commit"]) == 0
    capsys.readouterr()
    assert aide.main(["--repo", str(root), "merge", "27", "--no-test"]) == 0
    progress = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    _, _, status = aide._parse_item_status(progress.splitlines())
    assert status[27] == "in-review"


def test_gc_never_targets_an_item_awaiting_review(tmp_path: Path, capsys):
    """The load-bearing fix: `gc`'s ground is "the item is ✅", and a `pr`-mode
    item is no longer ✅ — so the exhaustion sweep cannot offer to delete the
    head branch of an open PR."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27", "in-review",
                      "--no-commit"]) == 0
    capsys.readouterr()
    assert aide.main(["--repo", str(root), "gc", "--yes"]) == 0
    assert "aide/027-bounds-rules" in _run(["git", "branch"], root).stdout
    assert "would delete" not in capsys.readouterr().out


def test_check_does_not_call_a_branch_awaiting_review_stale(tmp_path: Path, capsys):
    """A warning that fires on every run until a human merges is a warning
    that gets tuned out."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27", "in-review",
                      "--no-commit"]) == 0
    capsys.readouterr()
    aide.main(["--repo", str(root), "check"])
    assert "stale claim branch" not in capsys.readouterr().out


def test_status_does_not_recommend_gc_for_a_branch_awaiting_review(
        tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27", "in-review",
                      "--no-commit"]) == 0
    capsys.readouterr()
    aide.main(["--repo", str(root), "status"])
    out = capsys.readouterr().out
    assert "awaiting review" in out
    assert "run 'aide gc'" not in out


def test_sync_reports_a_review_item_whose_work_has_landed(tmp_path: Path, capsys):
    """🔍 needs a way home: in `pr` mode nothing in the loop observes the merge,
    so without this an item enters the state and never leaves it."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27",
                      "in-review"]) == 0
    _squash_merge(root, "aide/027-bounds-rules", "squash 027")
    capsys.readouterr()
    assert aide.main(["--repo", str(root), "sync"]) == 0
    out = capsys.readouterr().out
    assert "item 027 is 🔍" in out
    assert "progress set 027 done" in out


def test_sync_is_silent_about_a_review_item_still_awaiting_its_merge(
        tmp_path: Path, capsys):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27",
                      "in-review"]) == 0
    capsys.readouterr()
    assert aide.main(["--repo", str(root), "sync"]) == 0
    assert "is 🔍 but its work is now in" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# The tick reaches origin — regression: it was committed after the only push
# --------------------------------------------------------------------------- #
def test_auto_merge_pushes_the_commit_that_records_the_tick(tmp_path: Path):
    """`aide merge` writes the ✅ itself, so that commit must ride the push.

    Recorded after it, the tick was stranded on local main: origin's
    progress.md under-reported, and on a queue's last item nothing in the CLI
    would ever push it (`aide sync` only fetches and pulls).
    """
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="auto-merge")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "progress", "set", "27",
                      "in-review"]) == 0
    _run(["git", "push"], root)
    assert aide.main(["--repo", str(root), "merge", "27", "--no-test"]) == 0
    ahead = _run(["git", "rev-list", "--count", "origin/main..main"], root).stdout.strip()
    assert ahead == "0", "the ✅ commit never reached origin"
    _, _, status = aide._parse_item_status(
        _show_utf8(root, "origin/main:docs/aide/progress.md").splitlines())
    assert status[27] == "complete"


def test_merge_no_commit_leaves_the_tick_uncommitted(tmp_path: Path):
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/027-bounds-rules", "feature.txt")
    assert aide.main(["--repo", str(root), "merge", "27", "--no-test",
                      "--no-commit"]) == 0
    dirty = _run(["git", "status", "--porcelain"], root).stdout
    assert "progress.md" in dirty
    progress = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    _, _, status = aide._parse_item_status(progress.splitlines())
    assert status[27] == "complete"  # written, just not committed


# --------------------------------------------------------------------------- #
# A dependency awaiting review has not landed, so it still blocks
# --------------------------------------------------------------------------- #
def test_claim_skips_an_item_whose_dependency_is_only_in_review(tmp_path: Path):
    """Claiming off a base that lacks the dependency's work branches from a
    tree missing the very thing the dependency provides."""
    root = _init_repo(tmp_path / "r", mode="local")
    idir = root / "docs" / "aide" / "items"
    (idir / "027-bounds-rules.md").write_text(
        "# Item 027 — Bounds rules\n\n## Dependencies\n- Item 026 provides the engine.\n",
        encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-m", "spec"], root)
    # Downgrade 026 to 🔍 by hand: `progress set` never walks a status backwards.
    ppath = root / "docs" / "aide" / "progress.md"
    ppath.write_text(ppath.read_text(encoding="utf-8")
                     .replace("- ✅ Core. *(Item 026)*", "- 🔍 Core. *(Item 026)*"),
                     encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-m", "026 in review"], root)

    rc = aide.main(["--repo", str(root), "claim"])
    on = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
    assert on != "aide/027-bounds-rules", "claimed an item whose dependency is unmerged"
    # 028 has no dependencies, so claiming moves on to it rather than stalling.
    assert rc == 0 and on == "aide/028-coverage-rules"


# --------------------------------------------------------------------------- #
# gc reports what git did, not what was asked of it
# --------------------------------------------------------------------------- #
def test_gc_skips_a_branch_checked_out_in_another_worktree(tmp_path: Path, capsys):
    """`git branch -D` refuses a branch any worktree is sitting on, so the guard
    has to ask `git worktree list` — otherwise the preview promises a delete
    that then bounces off, which is the exact defect #70 was filed about."""
    root = _init_repo(tmp_path / "r", mode="local")
    _make_item_branch(root, "aide/026-rule-engine-core", "core.txt")
    _squash_merge(root, "aide/026-rule-engine-core", "squash 026")
    _run(["git", "worktree", "add", str(tmp_path / "wt"),
          "aide/026-rule-engine-core"], root)
    capsys.readouterr()
    # The PREVIEW must not promise it either — that is #70's first acceptance
    # criterion, "identical on every path", and a worktree is one of the paths.
    assert aide.main(["--repo", str(root), "gc"]) == 0
    previewed = _gc_lines(capsys)
    assert previewed == set()
    assert aide.main(["--repo", str(root), "gc", "--yes"]) == 0
    assert _gc_lines(capsys) == previewed
    assert "aide/026-rule-engine-core" in _run(["git", "branch"], root).stdout


def test_queue_start_refuses_a_name_that_exists_only_on_origin(tmp_path: Path, capsys):
    """It used to create the branch locally and then raise an uncaught
    CalledProcessError from the failing push — a traceback in an unattended flow."""
    remote = _mkbare(tmp_path / "remote.git")
    root = _init_repo(tmp_path / "r", mode="auto-merge")
    _run(["git", "remote", "add", "origin", str(remote)], root)
    _run(["git", "push", "-u", "origin", "main"], root)
    _run(["git", "switch", "-c", "aide/queue-016"], root)
    _run(["git", "push", "-u", "origin", "aide/queue-016"], root)
    _run(["git", "switch", "main"], root)
    _run(["git", "branch", "-D", "aide/queue-016"], root)
    _run(["git", "fetch", "origin"], root)
    capsys.readouterr()
    rc = aide.main(["--repo", str(root), "queue", "start", "16"])
    assert rc == 1
    assert "already exists on origin" in capsys.readouterr().err
