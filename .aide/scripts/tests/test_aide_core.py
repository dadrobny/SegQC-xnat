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
# structural icon positions (WI-1: prose is free, parsers are positionally strict)
# --------------------------------------------------------------------------- #
def test_structural_status_positions():
    assert aide._structural_status("- ✅ Core. *(Item 002)*") == "complete"
    assert aide._structural_status("| G1 Setup | Stage 0 | ✅ |") == "complete"
    assert aide._structural_status("## Stage 1 — Rules — 🚧") == "in-progress"
    # Icons in prose, mid-bullet, or a header title are plain text.
    assert aide._structural_status("The ✅ marks above are historical.") is None
    assert aide._structural_status("- Improve ✅ handling notes. *(Item 003)*") is None
    assert aide._structural_status("## Stage 2 — Polish ✅ handling") is None


def test_set_item_ignores_decoy_icon_in_prose():
    decoy = PROGRESS.replace(
        "**Acceptance.**\n- [ ] Rules fire.",
        "Note: the ✅ prose mark must not complete Item 003.\n\n"
        "**Acceptance.**\n- [ ] Rules fire.",
    )
    out = aide.set_item_status(decoy, 3, "in-progress")
    assert "- 🚧 Bounds. *(Item 003)*" in out
    assert "## Stage 1 — Rule Engine — 🚧" in out


def test_set_item_preserves_icons_in_title_cells_and_headers():
    decorated = (
        PROGRESS
        .replace("| 1 | Rule Engine | G2 | 🚧 |", "| 1 | Rule ✅ Engine | G2 | 🚧 |")
        .replace("## Stage 1 — Rule Engine — 🚧", "## Stage 1 — Rule ✅ Engine — 🚧")
    )
    out = aide.set_item_status(decorated, 3, "complete")
    # Only the Status cell / trailing header icon flip; the title icons survive.
    assert "| 1 | Rule ✅ Engine | G2 | ✅ |" in out
    assert "## Stage 1 — Rule ✅ Engine — ✅" in out


def test_parse_item_status_prose_icon_not_status():
    lines = (
        "## Stage 3 — X — 🚧\n"
        "**Deliverables.**\n"
        "- 📋 Thing. *(Item 050)*\n"
        "\n"
        "A prose note with ✅ that also mentions Item 051.\n"
    ).splitlines()
    _, _, status = aide._parse_item_status(lines)
    assert status[50] == "planned"
    # A prose mention carries no status at all — not even a decoy "planned"
    # (issue #15: only a deliverable bullet is a structural declaration).
    assert 51 not in status


def test_parse_item_status_ignores_table_notes_and_checkboxes():
    """conventions.md §1: only a deliverable bullet's leading icon is a status
    declaration. A verification-table Notes cell that narrates several item
    numbers, and an acceptance checkbox that merely cites its item, must not
    attribute any status to those items (issue #15) — each item's status comes
    only from its own deliverable bullet, if any.
    """
    lines = (
        "## Stage 14 — X — 🚧\n"
        "**Deliverables.**\n"
        "- ✅ Thing. *(Item 060)*\n"
        "\n"
        "| Check | Notes | Status |\n"
        "|---|---|---|\n"
        "| Env | Post-mortem mentions item 047, Item 084 at length | 🚧 |\n"
        "| Env2 | See Item 060 too | 📋 |\n"
        "\n"
        "**Acceptance.**\n"
        "- [x] Container runs the pipeline. *(Item 070; docker verified)*\n"
    ).splitlines()
    _, _, status = aide._parse_item_status(lines)
    assert status == {60: "complete"}  # only the deliverable bullet counts
    assert 47 not in status
    assert 84 not in status
    assert 70 not in status


def test_parse_item_status_wrapped_bullet_still_attributes():
    """A deliverable bullet that wraps onto a continuation line must still
    credit the reference to the bullet's own status — the reference belongs
    to the bullet it is part of, not to the physical line carrying the icon."""
    lines = (
        "## Stage 2 — X — 🚧\n"
        "**Deliverables.**\n"
        "- 📋 A long deliverable that wraps onto a\n"
        "  second line. *(Item 042)*\n"
    ).splitlines()
    _, _, status = aide._parse_item_status(lines)
    assert status[42] == "planned"


def test_parse_item_status_reads_every_number_in_a_multi_item_reference():
    """``*(Items A, B)*`` must credit B as well as A.

    The create-queue step tells authors to write exactly this form when one
    deliverable is delivered by several items. Reading only the first number
    orphaned the rest: they stayed "planned" on a ✅ bullet forever, which held
    their queue open and — since the live queue is the lowest-numbered open one
    — stranded ``aide claim`` on a finished queue.
    """
    lines = (
        "## Stage 6 — Reference — ✅\n"
        "**Deliverables.**\n"
        "- ✅ Ingestion and aggregation. *(Items 043, 044)*\n"
        "- ✅ Delta rules. *(Items 046, 047)*\n"
        "- ✅ Solo deliverable. *(Item 045)*\n"
    ).splitlines()
    _, _, status = aide._parse_item_status(lines)
    for num in (43, 44, 45, 46, 47):
        assert status[num] == "complete", f"item {num:03d} not credited"


def test_referenced_item_numbers_accepts_every_documented_form():
    """Single, comma list, slash list, hyphen range, en-dash range."""
    assert aide._referenced_item_numbers("*(Item 006)*") == [6]
    assert aide._referenced_item_numbers("*(Items 006, 044)*") == [6, 44]
    assert aide._referenced_item_numbers("Items 089/090 shipped") == [89, 90]
    assert aide._referenced_item_numbers("*(Items 089-092)*") == [89, 90, 91, 92]
    assert aide._referenced_item_numbers("*(Items 071–075)*") == [71, 72, 73, 74, 75]
    assert aide._referenced_item_numbers("no reference here") == []


def test_referenced_item_numbers_reads_lists_of_any_length():
    """A list is not capped at two — real documents enumerate three and more.

    SegQC-xnat's progress.md carries `*(Items 041, 053, 057)*` and
    `*(Items 066, 069, 070)*` on single deliverable bullets. Reading only the
    first two would orphan the tail exactly as reading only the first orphaned
    the rest.
    """
    assert aide._referenced_item_numbers("*(Items 006, 044, 045)*") == [6, 44, 45]
    assert aide._referenced_item_numbers("*(Items 041, 053, 057)*") == [41, 53, 57]
    assert aide._referenced_item_numbers(
        "*(Items 006, 044, 045, 046, 047)*") == [6, 44, 45, 46, 47]
    assert aide._referenced_item_numbers("*(Items 006/044/045)*") == [6, 44, 45]


def test_referenced_item_numbers_mixes_lists_and_ranges():
    """A list element may itself be a range."""
    assert aide._referenced_item_numbers("*(Items 006, 044-046)*") == [6, 44, 45, 46]
    assert aide._referenced_item_numbers("*(Items 071-073, 085)*") == [71, 72, 73, 85]


def test_referenced_item_numbers_tolerates_separator_spacing():
    """Authors write these by hand; spacing around separators must not matter."""
    for text in ("*(Items 006,044)*", "*(Items 006 , 044)*", "*(Items 006,  044)*"):
        assert aide._referenced_item_numbers(text) == [6, 44], text


def test_referenced_item_numbers_ignores_an_implausible_range():
    """A typo must not invent thousands of items — endpoints only."""
    assert aide._referenced_item_numbers("*(Items 6-9999)*") == [6, 9999]
    assert aide._referenced_item_numbers("*(Items 9-4)*") == [9, 4]


def test_status_parse_and_progress_set_agree_on_what_is_referenced():
    """One definition, so no caller can see a reference another cannot.

    They disagreed once: the status parse behind check/status/claim read only
    the first number of a list, while progress set matched any number literally
    present — so `progress set` acted on items `claim` believed untracked.
    """
    for line in ("- ✅ Thing. *(Items 055, 056)*",
                 "- ✅ Thing. *(Items 071–075)*",
                 "- ✅ Thing. *(Item 045)*"):
        for num in aide._referenced_item_numbers(line):
            assert aide._references_item(line, num)
        _, _, status = aide._parse_item_status(
            ["## Stage 6 — X — ✅", "**Deliverables.**", line])
        assert set(status) == set(aide._referenced_item_numbers(line))


def test_progress_set_flips_a_range_referenced_item(tmp_path: Path):
    """`aide progress set` must find an item named only inside a range."""
    progress = (
        "# P — Progress Tracker\n\n"
        "| Stage | Title | Objectives | Status |\n"
        "|-------|-------|-----------|--------|\n"
        "| 10 | Backend | G1 | 📋 |\n\n"
        "| Objective | Delivered by | Status |\n"
        "|-----------|--------------|--------|\n"
        "| G1 Backend | Stage 10 | 📋 |\n\n"
        "## Stage 10 — Backend — 📋\n\n"
        "**Deliverables.**\n\n"
        "- 📋 Backend port. *(Items 071–075)*\n\n"
        "**Acceptance.**\n\n"
        "- [ ] Backend works.\n"
    )
    out = aide.set_item_status(progress, 73, "complete")
    assert "- ✅ Backend port. *(Items 071–075)*" in out


def test_check_warns_on_stray_heading_icon(tmp_path: Path):
    """A heading's only structural slot is its trailing icon — one parked
    elsewhere on the same heading is a plausible misreading, so it still
    warns."""
    decoy = PROGRESS + "\n## 🚧 Notes — ✅\n"
    root = _docs(tmp_path, progress=decoy)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert errors == []
    assert any("status icon 🚧 outside" in w for w in warnings)


def test_check_silent_on_icons_in_prose(tmp_path: Path):
    """conventions.md §1 explicitly permits the icon vocabulary in prose, a
    non-leading bullet, and mid-bullet asides — none of those are structural
    positions, so none should trip the stray-icon lint (issue #13)."""
    decoy = PROGRESS + (
        "\nA stray ✅ in prose.\n\n"
        "- Flip the Stage 0 deliverable from 📋 to ✅ (mark it 🚧 while in progress).\n"
    )
    root = _docs(tmp_path, progress=decoy)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert errors == []
    assert not any("outside a structural status position" in w for w in warnings)


def test_check_no_stray_warning_on_clean_docs(tmp_path: Path):
    root = _docs(tmp_path)
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=[])
    assert not any("outside a structural status position" in w for w in warnings)


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


def test_check_two_declared_live_queues_is_not_an_error(tmp_path: Path):
    """Queue state is derived (WI-2): declared Status lines are decorative and
    can no longer produce the old 'more than one Live queue' error."""
    both_live = QUEUE_OLD.replace(
        "> **Status:** ✅ Completed — superseded by queue-002 (2026-06-01).",
        "> **Status:** Live · **Created:** 2026-06-01",
    )
    root = _docs(tmp_path, old=both_live)
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert errors == []


def test_check_warns_declared_live_but_derived_done(tmp_path: Path):
    # queue-001's only item (001) is ✅ in progress.md; declaring Live lies.
    stale = QUEUE_OLD.replace(
        "> **Status:** ✅ Completed — superseded by queue-002 (2026-06-01).",
        "> **Status:** Live · **Created:** 2026-06-01",
    )
    root = _docs(tmp_path, old=stale)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert errors == []
    assert any("declares 'Live' but every item is finished" in w for w in warnings)


def test_check_warns_declared_completed_but_derived_open(tmp_path: Path):
    # queue-002 still has 📋 item 003 but declares itself completed.
    lying = QUEUE_LIVE.replace(
        "> **Status:** Live · **Created:** 2026-07-01",
        "> **Status:** ✅ Completed — superseded by queue-003 (2026-07-02).",
    )
    root = _docs(tmp_path, live=lying)
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=[])
    assert any("marked completed but still has open items" in w for w in warnings)


def test_live_queue_text_is_lowest_open_regardless_of_declared_status(tmp_path: Path):
    # Neither queue declares anything; derived state alone must find queue-002
    # (item 003 is 📋) and skip queue-001 (item 001 is ✅).
    root = _docs(
        tmp_path,
        live=QUEUE_LIVE.replace("> **Status:** Live · **Created:** 2026-07-01",
                                "> **Created:** 2026-07-01"),
        old=QUEUE_OLD.replace(
            "> **Status:** ✅ Completed — superseded by queue-002 (2026-06-01).",
            "> **Created:** 2026-06-01"),
    )
    cfg = aide.load_config(root)
    text = aide._live_queue_text(root, cfg, None)
    assert text is not None and "Work Queue 002" in text


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
# outcome targets (issue #14: shipped work vs. achieved goal are orthogonal)
# --------------------------------------------------------------------------- #
TARGETS = """\

## Outcome targets

| Target | Objective | Attempted by | Status | Evidence / follow-up |
|--------|-----------|--------------|--------|----------------------|
| Held-out FPR <= 0.10 | G2 | Stage 1 | ❌ Not met | FPR 0.975 → gap insight |
| Runtime < 60 s | G1 | Stage 0 | ✅ Met (2026-07-01, CI) | timing job |
"""


def test_outcome_targets_parse():
    ts = aide.outcome_targets((PROGRESS + TARGETS).splitlines())
    assert [(t.text, t.objectives, t.kind) for t in ts] == [
        ("Held-out FPR <= 0.10", ["G2"], "not-met"),
        ("Runtime < 60 s", ["G1"], "met"),
    ]


def test_outcome_targets_absent_table_is_empty():
    assert aide.outcome_targets(PROGRESS.splitlines()) == []


def test_outcome_targets_multi_objective_and_unverified():
    ts = aide.outcome_targets(
        "## Outcome targets\n"
        "| Target | Objective | Attempted by | Status | Notes |\n"
        "|---|---|---|---|---|\n"
        "| Dice >= 0.9 | G1, G3 | Stage 2 | ❓ Unverified | pending cohort |\n"
        .splitlines())
    assert ts[0].objectives == ["G1", "G3"]
    assert ts[0].kind == "unverified"


def test_unmet_target_blocks_objective_rollup_not_stage():
    out = aide.set_item_status(PROGRESS + TARGETS, 3, "complete")
    # The stage closes: its planned work shipped.
    assert "## Stage 1 — Rule Engine — ✅" in out
    assert "| 1 | Rule Engine | G2 | ✅ |" in out
    assert "- [x] Rules fire." in out
    # The objective does not: its outcome target is ❌ Not met.
    assert "| G2 Rules | Stage 1 | 🚧 |" in out


def test_met_target_does_not_block_objective():
    met = (PROGRESS + TARGETS).replace("❌ Not met", "✅ Met (2026-07-02, eval run)")
    out = aide.set_item_status(met, 3, "complete")
    assert "| G2 Rules | Stage 1 | ✅ |" in out


def test_check_clean_with_targets_table(tmp_path: Path):
    root = _docs(tmp_path, progress=PROGRESS + TARGETS)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert errors == [], errors
    assert not any("outcome target" in w for w in warnings), warnings


def test_check_flags_objective_complete_over_unmet_target(tmp_path: Path):
    lying = (PROGRESS + TARGETS).replace(
        "| G2 Rules | Stage 1 | 🚧 |", "| G2 Rules | Stage 1 | ✅ |")
    root = _docs(tmp_path, progress=lying)
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("objective G2 marked ✅ but outcome target" in e for e in errors)


def test_check_warns_objective_complete_over_unverified_target(tmp_path: Path):
    doc = (PROGRESS + TARGETS).replace("❌ Not met", "❓ Unverified").replace(
        "| G2 Rules | Stage 1 | 🚧 |", "| G2 Rules | Stage 1 | ✅ |")
    root = _docs(tmp_path, progress=doc)
    cfg = aide.load_config(root)
    errors, warnings = aide.run_checks(root, cfg, branches=[])
    assert not any("outcome target" in e for e in errors)
    assert any("is not ✅ Met" in w for w in warnings)


def test_check_warns_unrecognised_target_status(tmp_path: Path):
    doc = (PROGRESS + TARGETS).replace("❌ Not met", "TBD")
    root = _docs(tmp_path, progress=doc)
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=[])
    assert any("unrecognised Status" in w for w in warnings)


# --------------------------------------------------------------------------- #
# template residue ({{slot}} left unfilled in a generated document)
# --------------------------------------------------------------------------- #
def test_template_residue_flags_unfilled_slot(tmp_path: Path):
    root = _docs(tmp_path, progress=PROGRESS.replace("Scaffolding", "{{title}}"))
    cfg = aide.load_config(root)
    errors, _ = aide.run_checks(root, cfg, branches=[])
    assert any("unfilled template slot {{title}}" in e for e in errors)


def test_template_residue_silent_on_filled_docs(tmp_path: Path):
    root = _docs(tmp_path)
    ddir = root / "docs" / "aide"
    assert aide.template_residue_errors(ddir) == []


def test_template_residue_scans_items_dir(tmp_path: Path):
    root = _docs(tmp_path)
    ddir = root / "docs" / "aide"
    (ddir / "items" / "002-core.md").write_text(
        "# Item 002 — {{title}}\n", encoding="utf-8"
    )
    errors = aide.template_residue_errors(ddir)
    assert any("002-core.md" in e and "{{title}}" in e for e in errors)


# --------------------------------------------------------------------------- #
# insight inbox (WI-4)
# --------------------------------------------------------------------------- #
def test_insight_entries_well_formed(tmp_path: Path):
    root = _docs(tmp_path)
    (root / "docs" / "aide" / "insights.md").write_text(
        "# Insight Inbox\n\n"
        "- [ ] automation — venv rebuild is manual every time. *(item 003, 2026-07-18)*\n"
        "- [x] knowledge — pytest needs -p no:cacheprovider on CI. *(2026-07-01)* → CLAUDE.md\n"
        "- [ ] framework — aide merge misreports branch deletion. *(item 002, 2026-07-18)*\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=[])
    assert not any("insights.md" in w for w in warnings)


def test_insight_malformed_entry_warns(tmp_path: Path):
    root = _docs(tmp_path)
    (root / "docs" / "aide" / "insights.md").write_text(
        "# Insight Inbox\n\n"
        "- [ ] misc — unknown type. *(2026-07-18)*\n"
        "- [ ] defect no separator or provenance\n",
        encoding="utf-8",
    )
    cfg = aide.load_config(root)
    _, warnings = aide.run_checks(root, cfg, branches=[])
    assert sum("insights.md" in w for w in warnings) == 2


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


def test_cli_progress_set_untracked_item_errors(tmp_path: Path, capsys):
    """An item no deliverable bullet references must fail loudly, not silently
    no-op as 'already >= done' (the Stage-5 tracking-blind-spot regression)."""
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "progress", "set", "777", "done", "--no-commit"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no deliverable in progress.md references 'Item 777'" in err
    # progress.md is left untouched.
    text = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    assert text == PROGRESS


def test_cli_progress_set_backfills_reference_from_spec(tmp_path: Path, capsys):
    """A missed queue back-fill self-heals: the reference is inserted from the
    item spec's Stage header instead of hard-erroring (WI-7)."""
    root = _docs(tmp_path)
    (root / "docs" / "aide" / "items" / "004-extra-thing.md").write_text(
        "# Item 004 — Extra thing\n\n"
        "> **Created:** 2026-07-18 · status tracked in progress.md\n"
        "> **Stage:** 1 — Rule Engine\n",
        encoding="utf-8",
    )
    rc = aide.main(["--repo", str(root), "progress", "set", "4", "in-progress", "--no-commit"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "back-filled missing deliverable reference under Stage 1" in out
    text = (root / "docs" / "aide" / "progress.md").read_text(encoding="utf-8")
    assert "- 🚧 Extra thing. *(Item 004)*" in text
    # Existing deliverables untouched; stage still in progress.
    assert "- 📋 Bounds. *(Item 003)*" in text
    assert "## Stage 1 — Rule Engine — 🚧" in text


def test_cli_status_reports_queues_and_claims(tmp_path: Path, capsys):
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "status", "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "queue-001.md: done" in out
    assert "queue-002.md: open (live)" in out
    assert "003" in out  # the open item is listed


def test_cli_queue_tidy_edits_file(tmp_path: Path):
    root = _docs(tmp_path)
    rc = aide.main(["--repo", str(root), "queue", "tidy", "1", "--date", "2026-07-02"])
    assert rc == 0
    text = (root / "docs" / "aide" / "queue" / "queue-001.md").read_text(encoding="utf-8")
    assert "Completed — superseded by queue-002 (2026-07-02)" in text
