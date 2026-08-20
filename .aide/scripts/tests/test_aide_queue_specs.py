"""Tests for ``aide check --queue`` — a queue's specs checked against each other.

The window this guards is the one ``/aide-spec-queue`` creates: N specs authored
on one branch before any is built, where every cross-item conflict is possible
and cheap to fix, and nothing looked.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_qspecs", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"
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
- 📋 A. *(Item 027)*
- 📋 B. *(Item 028)*

**Acceptance.**
- [ ] Rules fire.
"""


def _spec_text(num: int, may=(), asserts=(), deps="None.") -> str:
    lines = [f"# Item {num:03d} — Demo", "", "## Authorised paths", ""]
    if may:
        lines += ["**May change:**", ""]
        lines += [f"- `{p}` — work" for p in may]
        lines.append("")
    if asserts:
        lines += ["**Asserts against:**", ""]
        lines += [f"- `{p}` — pinned" for p in asserts]
        lines.append("")
    lines += ["## Dependencies", "", deps, ""]
    return "\n".join(lines)


def _make_repo(tmp_path: Path, specs: dict, queue_items=(27, 28)) -> Path:
    repo = tmp_path / "repo"
    d = repo / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (d / "items").mkdir(parents=True)
    (repo / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    (d / "progress.md").write_text(PROGRESS, encoding="utf-8")
    body = "\n\n".join(f"### Item {n:03d}: Thing {n}\nDoes a thing."
                       for n in queue_items)
    (d / "queue" / "queue-003.md").write_text(f"# Demo — Work Queue 003\n\n{body}\n",
                                              encoding="utf-8")
    for num, text in specs.items():
        (d / "items" / f"{num:03d}-thing.md").write_text(text, encoding="utf-8")
    return repo


def _findings(repo: Path, queue: int = 3):
    cfg = aide.load_config(repo)
    return aide.queue_spec_findings(repo, cfg, queue)


# --------------------------------------------------------------------------- #
# patterns_overlap
# --------------------------------------------------------------------------- #
def test_overlap_identical_patterns():
    assert aide.patterns_overlap("src/a.py", "src/a.py")


def test_overlap_subtree_swallows_a_file():
    assert aide.patterns_overlap("src/**", "src/deep/a.py")
    assert aide.patterns_overlap("src/deep/a.py", "src/**")


def test_overlap_glob_covers_a_literal():
    assert aide.patterns_overlap("tests/golden/*.json", "tests/golden/a.json")


def test_no_overlap_between_unrelated_paths():
    assert not aide.patterns_overlap("src/a.py", "src/b.py")
    assert not aide.patterns_overlap("src/**", "tests/a.py")
    assert not aide.patterns_overlap("tests/golden/*.json", "tests/golden/deep/a.json")


def test_two_unrelated_globs_are_not_guessed_at():
    """Deciding that `src/*.py` and `src/a*` might one day both match `src/ab.py`
    would mean guessing at a future tree. The check reports what it can prove."""
    assert not aide.patterns_overlap("src/*.py", "src/a*")


# --------------------------------------------------------------------------- #
# row 1 — two specs claim the same file
# --------------------------------------------------------------------------- #
def test_reports_two_items_claiming_the_same_path(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/shared.py"]),
        28: _spec_text(28, may=["src/shared.py"]),
    })
    findings, _ = _findings(repo)
    kinds = [f.kind for f in findings]
    assert "may-change-overlap" in kinds
    hit = next(f for f in findings if f.kind == "may-change-overlap")
    assert hit.items == (27, 28) and hit.severity == "warning"


def test_subtree_claim_overlapping_a_sibling_file_is_reported(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/**"]),
        28: _spec_text(28, may=["src/one.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "may-change-overlap" for f in findings)


def test_disjoint_specs_produce_no_findings(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, unspecced = _findings(repo)
    assert findings == [] and unspecced == []


# --------------------------------------------------------------------------- #
# rows 2+3 — one spec changes what another pins
# --------------------------------------------------------------------------- #
def test_changing_a_siblings_pinned_path_is_an_error(tmp_path: Path):
    """The recorded shape: item 101 was authorised to edit exactly the files
    items 099/100 had pinned as untouched forever."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "changes-pinned-state")
    assert hit.severity == "error"
    assert hit.items == (27, 28)
    assert "027" in hit.message and "028" in hit.message


def test_a_live_recomputed_pin_is_caught_like_a_byte_hash(tmp_path: Path):
    """The instance a fragile-hash survey missed: item 105's AC7 recomputed its
    evidence live, so it was *more* coupled to the state item 106 changed."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/feature_docs.py"]),
        28: _spec_text(28, may=["docs/table.md"],
                       asserts=["src/feature_docs.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" for f in findings)


def test_pinning_a_path_nobody_changes_is_fine(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"], asserts=["src/untouched.py"]),
    })
    findings, _ = _findings(repo)
    assert findings == []


# --------------------------------------------------------------------------- #
# row 5 — the dependency graph
# --------------------------------------------------------------------------- #
def test_dependency_cycle_is_an_error(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "dependency-cycle")
    assert hit.severity == "error"
    assert set(hit.items) == {27, 28}


def test_a_downstream_aside_does_not_create_a_cycle(tmp_path: Path):
    """`**Downstream` marks a forward reference, not a blocker — a plain
    'item NNN depends on this' aside used to register backwards."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"],
                       deps="None.\n\n**Downstream:** item 028 depends on this."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert not any(f.kind == "dependency-cycle" for f in findings)


def test_unknown_dependency_is_a_warning(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 999 provides it."),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "unknown-dependency")
    assert hit.severity == "warning" and hit.items == (27, 999)


def test_dependency_on_a_real_earlier_item_is_not_flagged(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert findings == []


# --------------------------------------------------------------------------- #
# graceful degradation
# --------------------------------------------------------------------------- #
def test_undeclared_spec_is_reported_never_skipped(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: "# Item 027 — Demo\n\n## Description\n\nNo authorised paths here.\n",
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "undeclared-scope")
    assert hit.severity == "warning" and hit.items == (27,)
    assert "human scope review" in hit.message


def test_unspecced_items_are_counted_not_flagged(tmp_path: Path):
    """A queued item with no spec yet is the normal mid-queue state — that is
    what /aide-spec-queue exists to fill, not a conflict."""
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    findings, unspecced = _findings(repo)
    assert unspecced == [28]
    assert findings == []


def test_bookkeeping_files_are_not_an_overlap(tmp_path: Path):
    """Every item writes progress.md and insights.md — `aide scope` authorises
    both without them being listed. Two items 'conflicting' over progress.md is
    the claim protocol working, not a conflict. Observed as 4 of 16 warnings on
    a real consumer queue before this exclusion."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py", "docs/aide/progress.md",
                                "docs/aide/insights.md"]),
        28: _spec_text(28, may=["src/b.py", "docs/aide/progress.md",
                                "docs/aide/insights.md"]),
    })
    findings, _ = _findings(repo)
    assert findings == []


def test_pinning_a_bookkeeping_file_is_still_reported(tmp_path: Path):
    """The exclusion is for the overlap check only — pinning progress.md is a
    real assertion, and changing it under one is a real break."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["docs/aide/progress.md"]),
        28: _spec_text(28, may=["src/b.py"], asserts=["docs/aide/progress.md"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" for f in findings)


def test_a_spec_that_only_pins_is_still_compared(tmp_path: Path):
    """An empty May change is not 'nothing declared'. A stage-validation item
    changes only the bookkeeping every item may write, while pinning the tree
    it validates — treating that as undeclared would drop exactly the specs
    whose whole purpose is to assert, and miss siblings breaking their pins."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, asserts=["src/a.py"]),
    })
    findings, _ = _findings(repo)
    kinds = [f.kind for f in findings]
    assert "changes-pinned-state" in kinds
    assert "undeclared-scope" not in kinds


def test_a_section_with_both_lists_empty_is_undeclared(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "undeclared-scope" and f.items == (27,) for f in findings)


def test_report_without_queue_is_refused(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    rc = aide.main(["--repo", str(repo), "check", "--report",
                    str(tmp_path / "out.json")])
    assert rc == 2
    assert "--report needs --queue" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists()


def test_missing_queue_file_is_an_error(tmp_path: Path):
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    findings, _ = _findings(repo, queue=99)
    assert findings[0].kind == "missing-queue"


# --------------------------------------------------------------------------- #
# the command
# --------------------------------------------------------------------------- #
def test_check_queue_fails_on_an_error_finding(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    rc = aide.main(["--repo", str(repo), "check", "--queue", "3"])
    assert rc == 1
    assert "Asserts against" in capsys.readouterr().out


def test_check_without_queue_is_unchanged(tmp_path: Path, capsys):
    """The cross-spec checks are opt-in: a bare `aide check` must not start
    reporting them."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert "Asserts against" not in capsys.readouterr().out


def test_report_writes_the_json_seam(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    out = tmp_path / "status" / "queue-003.json"
    aide.main(["--repo", str(repo), "check", "--queue", "3", "--report", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["queue"] == 3
    assert payload["unspecced_items"] == []
    kinds = [f["kind"] for f in payload["findings"]]
    assert "changes-pinned-state" in kinds
    assert payload["findings"][0]["items"] == [27, 28]
