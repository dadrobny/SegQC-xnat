"""Tests for the base-ref layer — what a claim branches off and merges back to.

``main_branch`` stays the default everywhere; these cover the two ways a branch
can legitimately have a different base (an explicit ``--base``, and the base a
claim recorded when it branched off a queue branch) and the verbs that read it.

Repositories are built under ``tmp_path`` in ``git.mode = "local"`` so nothing
pushes, fetches, or touches the real project.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_base", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"

[git]
mode = "local"
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
- 📋 Bounds. *(Item 027)*
- 📋 Coverage. *(Item 028)*

**Acceptance.**
- [ ] Rules fire.
"""

QUEUE = """\
# Demo — Work Queue 003

### Item 027: Bounds rules
Bounds.

### Item 028: Coverage rules
Coverage.
"""

SPEC_027 = """\
# Item 027 — Bounds rules

## Authorised paths

**May change:**

- `src/demo/bounds.py` — the rule
"""


def _run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "Tester"], path)
    (path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    d = path / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (d / "items").mkdir(parents=True)
    (d / "progress.md").write_text(PROGRESS, encoding="utf-8")
    (d / "queue" / "queue-003.md").write_text(QUEUE, encoding="utf-8")
    (d / "items" / "027-bounds-rules.md").write_text(SPEC_027, encoding="utf-8")
    (path / "src" / "demo").mkdir(parents=True)
    (path / "src" / "demo" / "bounds.py").write_text("x = 1\n", encoding="utf-8")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)
    return path


def _branches(path: Path) -> list:
    out = _run(["git", "branch", "--format=%(refname:short)"], path).stdout
    return [b.strip() for b in out.splitlines() if b.strip()]


def _commit(path: Path, rel: str, text: str, message: str) -> None:
    target = path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", message], path)


# --------------------------------------------------------------------------- #
# resolve_base
# --------------------------------------------------------------------------- #
def test_resolve_base_defaults_to_main_branch(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    cfg = aide.load_config(repo)
    assert aide.resolve_base(repo, cfg) == "main"


def test_resolve_base_prefers_the_recorded_base(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    cfg = aide.load_config(repo)
    aide._record_branch_base(repo, "main", "aide/queue-003")
    assert aide.resolve_base(repo, cfg, branch="main") == "aide/queue-003"


def test_resolve_base_explicit_wins_over_recorded(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    cfg = aide.load_config(repo)
    aide._record_branch_base(repo, "main", "aide/queue-003")
    assert aide.resolve_base(repo, cfg, "release/1.x", branch="main") == "release/1.x"


def test_recorded_base_is_absent_by_default(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    assert aide._recorded_branch_base(repo, "main") is None


# --------------------------------------------------------------------------- #
# claim records a base
# --------------------------------------------------------------------------- #
def test_claim_from_main_records_main(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    assert aide.main(["--repo", str(repo), "claim"]) == 0
    branch = "aide/027-bounds-rules"
    assert branch in _branches(repo)
    assert aide._recorded_branch_base(repo, branch) == "main"


def test_claim_from_a_queue_branch_records_that_branch(tmp_path: Path, capsys):
    """`switch -c` already branches from whatever is checked out, so claiming
    from a queue branch branched correctly all along — only the merge target
    was hard-wired. The base is inferred here so no caller must pass a flag."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    assert aide.main(["--repo", str(repo), "claim"]) == 0
    assert aide._recorded_branch_base(repo, "aide/027-bounds-rules") == "aide/queue-003"
    assert "base aide/queue-003" in capsys.readouterr().out


def test_claim_does_not_infer_a_base_from_an_arbitrary_branch(tmp_path: Path):
    """Only a *recognised* queue branch is inferred from. Inferring from any
    checked-out branch would silently retarget a merge."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "spike/whatever"], repo)
    assert aide.main(["--repo", str(repo), "claim"]) == 0
    assert aide._recorded_branch_base(repo, "aide/027-bounds-rules") == "main"


def test_claim_explicit_base_overrides_the_inference(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    assert aide.main(["--repo", str(repo), "claim", "--base", "main"]) == 0
    assert aide._recorded_branch_base(repo, "aide/027-bounds-rules") == "main"


def test_claim_dry_run_names_the_base_and_creates_nothing(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    assert "base aide/queue-003" in capsys.readouterr().out
    assert "aide/027-bounds-rules" not in _branches(repo)


# --------------------------------------------------------------------------- #
# merge honours the base
# --------------------------------------------------------------------------- #
def test_merge_lands_on_the_recorded_base_not_main(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    assert aide.main(["--repo", str(repo), "merge", "27", "--no-test"]) == 0
    assert _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip() == "aide/queue-003"
    assert "x = 2" in (repo / "src" / "demo" / "bounds.py").read_text(encoding="utf-8")

    _run(["git", "switch", "main"], repo)
    assert "x = 1" in (repo / "src" / "demo" / "bounds.py").read_text(encoding="utf-8")


def test_merge_base_flag_overrides_the_recorded_base(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    assert aide.main(["--repo", str(repo), "merge", "27", "--base", "main",
                      "--no-test"]) == 0
    _run(["git", "switch", "main"], repo)
    assert "x = 2" in (repo / "src" / "demo" / "bounds.py").read_text(encoding="utf-8")


def test_merge_without_a_recorded_base_still_lands_on_main(tmp_path: Path):
    """main_branch is the default and is never removed as one."""
    repo = _init_repo(tmp_path / "repo")
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    assert aide.main(["--repo", str(repo), "merge", "27", "--no-test"]) == 0
    assert _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip() == "main"


def test_merge_reports_a_base_that_does_not_exist(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    rc = aide.main(["--repo", str(repo), "merge", "27", "--base", "no/such",
                    "--no-test"])
    assert rc == 1
    assert "no such local branch" in capsys.readouterr().err


def test_merge_refuses_a_base_that_is_not_a_local_branch(tmp_path: Path, capsys):
    """`git switch` on a tag/commit/remote-tracking ref detaches HEAD, and a
    merge into a detached HEAD updates no branch while still reporting success
    — then the claim branch is deleted and the work survives only as an
    unreferenced commit. Resolving is not enough; it must be a branch."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "tag", "v1"], repo)
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    rc = aide.main(["--repo", str(repo), "merge", "27", "--base", "v1",
                    "--no-test"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "detach" in err
    assert "aide/027-bounds-rules" in _branches(repo), "claim branch must survive"


def test_claim_branches_from_the_base_not_from_head(tmp_path: Path):
    """`switch -c` with no start point uses HEAD, which would let the branch's
    real starting point disagree with the base it records — claiming with
    `--base main` from a queue branch would start from the queue branch and
    then merge all of it into main."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    _commit(repo, "queue_only.py", "q = 1\n", "queue-branch-only work")

    assert aide.main(["--repo", str(repo), "claim", "--base", "main"]) == 0
    assert not (repo / "queue_only.py").exists(), (
        "claim recorded main as the base, so it must branch from main")


def test_claim_refuses_a_base_that_is_not_a_local_branch(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "tag", "v1"], repo)
    rc = aide.main(["--repo", str(repo), "claim", "--base", "v1"])
    assert rc == 1
    assert "not a local branch" in capsys.readouterr().err
    assert "aide/027-bounds-rules" not in _branches(repo)


def test_scope_uses_an_explicit_base_verbatim(tmp_path: Path, capsys):
    """An explicit --base is the caller's word: substituting origin/ for it
    would make `--base main` mean something they did not write."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/027-bounds-rules"], repo)
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    assert aide.main(["--repo", str(repo), "scope", "--base", "main"]) == 0
    assert "vs main" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the base reaches the other verbs
# --------------------------------------------------------------------------- #
def test_scope_diffs_against_the_recorded_base(tmp_path: Path, capsys):
    """An item claimed from a queue branch has diverged from *that*. Diffing
    against main would report every sibling item already merged into the queue
    as this item's own out-of-scope change."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    _commit(repo, "unrelated/sibling.py", "s = 1\n", "an earlier item, on the queue branch")
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "this item's own work")

    assert aide.main(["--repo", str(repo), "scope"]) == 0
    out = capsys.readouterr().out
    assert "aide/queue-003" in out and "1 changed file(s)" in out


def test_scope_without_a_recorded_base_uses_main(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/027-bounds-rules"], repo)
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")

    assert aide.main(["--repo", str(repo), "scope"]) == 0
    assert "vs main" in capsys.readouterr().out


def test_gc_merged_is_measured_against_the_base(tmp_path: Path, capsys):
    """A branch merged into the queue branch is not merged into main, so a
    main-only --merged finds nothing where the cleanup actually is."""
    repo = _init_repo(tmp_path / "repo")
    _run(["git", "switch", "-c", "aide/queue-003"], repo)
    aide.main(["--repo", str(repo), "claim"])
    _commit(repo, "src/demo/bounds.py", "x = 2\n", "work")
    _run(["git", "switch", "aide/queue-003"], repo)
    _run(["git", "merge", "--no-edit", "aide/027-bounds-rules"], repo)

    assert aide.main(["--repo", str(repo), "gc", "--merged"]) == 0
    assert "aide/027-bounds-rules" in capsys.readouterr().out

    assert aide.main(["--repo", str(repo), "gc", "--merged", "--base", "main"]) == 0
    assert "aide/027-bounds-rules" not in capsys.readouterr().out


def test_status_accepts_a_base_and_still_reports(tmp_path: Path, capsys):
    repo = _init_repo(tmp_path / "repo")
    assert aide.main(["--repo", str(repo), "status", "--base", "main",
                      "--no-fetch"]) == 0
    assert "aide status" in capsys.readouterr().out
