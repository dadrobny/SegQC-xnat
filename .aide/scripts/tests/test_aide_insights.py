"""Tests for `aide insights` — list / tick / archive over the inbox.

The inbox is the one living document whose contract is *immutability of the
claim*, so the assertions here are mostly about what the verbs must NOT do:
never reword a captured line, never move an open entry out of the live file,
never renumber silently. The pure helpers are exercised directly; the command
layer is driven through `aide.main` in a real git repo, the way a consumer runs
it.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_insights", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]

AIDE_TOML = ('[project]\nname = "Demo"\ndocs_dir = "docs/aide"\n\n'
             '[git]\nmode = "local"\nmain_branch = "main"\nbranch_prefix = "aide/"\n')

INBOX = """\
# Insight Inbox

_Entries below, newest last._

- [x] framework — insights.md has no verb *(item 117, 2026-03-04)* → aide-loop #52
  - **2026-03-05** → accepted into wave 3
- [ ] defect — the reach check calls its own happy path a typo *(2026-05-11)*
- [x] knowledge — utf-8-sig is the right default for hand-edited files *(2026-07-02)* → conventions.md
- [ ] gap — nothing exercises an installed engine *(item 118, 2026-08-15)*
"""


def _run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _repo(tmp_path: Path, inbox: str = INBOX) -> Path:
    repo = tmp_path / "repo"
    d = repo / "docs" / "aide"
    d.mkdir(parents=True)
    (repo / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    (d / "insights.md").write_text(inbox, encoding="utf-8")
    _run(["git", "init", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@e.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "init"], repo)
    return repo


def _inbox(repo: Path) -> str:
    return (repo / "docs" / "aide" / "insights.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# parse_insights
# --------------------------------------------------------------------------- #
def test_parse_reads_every_field():
    entries = aide.parse_insights(INBOX)
    assert [e.ordinal for e in entries] == [1, 2, 3, 4]
    first = entries[0]
    assert (first.ticked, first.type, first.date, first.item) == (
        True, "framework", "2026-03-04", 117)
    assert first.pointer == "aide-loop #52"
    assert first.trail == ["  - **2026-03-05** → accepted into wave 3"]
    assert entries[1].ticked is False and entries[1].item is None


def test_a_trail_line_is_not_mistaken_for_an_entry():
    """Indentation is the only thing separating the two shapes."""
    entries = aide.parse_insights(INBOX)
    assert len(entries) == 4
    assert all("**2026-03-05**" not in e.text for e in entries)


def test_malformed_entry_still_occupies_an_ordinal():
    """Otherwise `list`'s numbers stop matching the file after the first typo."""
    text = INBOX + "- this is not an entry\n- [ ] defect — no provenance at all\n"
    entries = aide.parse_insights(text)
    assert [e.ordinal for e in entries] == [1, 2, 3, 4, 5, 6]
    assert entries[4].type is None and entries[5].type is None


def test_a_claim_containing_parentheses_parses():
    text = "- [ ] gap — the venv (the one aide env builds) is never checked *(2026-08-01)*\n"
    entry = aide.parse_insights(text)[0]
    assert entry.type == "gap" and entry.date == "2026-08-01"
    assert "(the one aide env builds)" in entry.text


# --------------------------------------------------------------------------- #
# tick_insight_text
# --------------------------------------------------------------------------- #
def test_tick_flips_the_box_and_records_where_it_landed():
    out, msg = aide.tick_insight_text(INBOX, 2, "item 121", "2026-08-24")
    line = out.splitlines()[6]
    assert line.startswith("- [x] defect — the reach check calls its own happy path a typo")
    assert line.endswith("*(2026-05-11)* → item 121")
    assert "ticked" in msg


def test_tick_never_touches_the_claim():
    out, _ = aide.tick_insight_text(INBOX, 4, "item 122", "2026-08-24")
    assert "nothing exercises an installed engine *(item 118, 2026-08-15)*" in out
    # And no other entry moved.
    assert aide.parse_insights(out)[1].raw == aide.parse_insights(INBOX)[1].raw


def test_ticking_an_already_ticked_entry_appends_a_dated_trail_line():
    """The second routing is bookkeeping, and bookkeeping is appendable."""
    out, msg = aide.tick_insight_text(INBOX, 1, "resolved in engine 1.17.0", "2026-08-24")
    lines = out.splitlines()
    assert lines[5] == "  - **2026-03-05** → accepted into wave 3"
    assert lines[6] == "  - **2026-08-24** → resolved in engine 1.17.0"
    assert "already ticked" in msg
    # The entry line itself is byte-identical.
    assert lines[4] == INBOX.splitlines()[4]


def test_trail_line_is_appended_newest_last():
    once, _ = aide.tick_insight_text(INBOX, 1, "first", "2026-08-24")
    twice, _ = aide.tick_insight_text(once, 1, "second", "2026-08-25")
    trail = aide.parse_insights(twice)[0].trail
    assert [t.split("→ ")[1] for t in trail] == [
        "accepted into wave 3", "first", "second"]


def test_ticking_an_entry_that_already_has_a_pointer_keeps_it():
    text = "- [ ] gap — a claim routed by hand *(2026-08-01)* → docs/notes.md\n"
    out, msg = aide.tick_insight_text(text, 1, "item 130", "2026-08-24")
    assert out.splitlines()[0].endswith("*(2026-08-01)* → docs/notes.md")
    assert out.splitlines()[0].startswith("- [x]")
    assert out.splitlines()[1] == "  - **2026-08-24** → item 130"
    assert "kept" in msg


def test_tick_rejects_an_ordinal_that_does_not_exist():
    try:
        aide.tick_insight_text(INBOX, 9, "item 121", "2026-08-24")
    except ValueError as exc:
        assert "no entry 9" in str(exc) and "insights list" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_tick_refuses_a_pointer_containing_a_line_break():
    """A break would split one claim into two and renumber everything below."""
    for bad in ("item 121\nnot a claim", "item 121\r- [ ] forged", "a\rb"):
        try:
            aide.tick_insight_text(INBOX, 2, bad, "2026-08-24")
        except ValueError as exc:
            assert "line break" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_a_rejected_pointer_leaves_the_file_untouched(tmp_path: Path):
    repo = _repo(tmp_path)
    before = _inbox(repo)
    assert aide.main(["--repo", str(repo), "insights", "tick", "2",
                      "--pointer", "item 121\n- [ ] forged entry",
                      "--no-commit"]) == 1
    assert _inbox(repo) == before
    assert len(aide.parse_insights(_inbox(repo))) == 4


def test_tick_refuses_a_malformed_entry_rather_than_guessing():
    text = "- [ ] defect no separator and no provenance\n"
    try:
        aide.tick_insight_text(text, 1, "item 121", "2026-08-24")
    except ValueError as exc:
        assert "does not parse" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# --------------------------------------------------------------------------- #
# archive_insight_text
# --------------------------------------------------------------------------- #
def test_archive_moves_only_closed_entries_older_than_the_date():
    remaining, moved = aide.archive_insight_text(INBOX, "2026-06-01")
    assert list(moved) == ["2026-Q1"]
    assert len(aide.parse_insights(remaining)) == 3
    assert "insights.md has no verb" not in remaining


def test_archive_never_moves_an_open_entry_however_old():
    """The open backlog is the working set; archiving it hides what list exists for."""
    remaining, moved = aide.archive_insight_text(INBOX, "2027-01-01")
    kept = aide.parse_insights(remaining)
    assert all(not e.ticked for e in kept)
    assert [e.date for e in kept] == ["2026-05-11", "2026-08-15"]
    assert sum(len(v) for v in moved.values()) == 3  # two entries + one trail line


def test_archive_carries_the_status_trail_with_its_entry():
    _, moved = aide.archive_insight_text(INBOX, "2026-06-01")
    assert moved["2026-Q1"] == [
        "- [x] framework — insights.md has no verb *(item 117, 2026-03-04)* → aide-loop #52",
        "  - **2026-03-05** → accepted into wave 3",
    ]


def test_archive_moves_lines_byte_for_byte():
    original = INBOX.splitlines()
    _, moved = aide.archive_insight_text(INBOX, "2026-08-01")
    for lines in moved.values():
        for line in lines:
            assert line in original


def test_archive_groups_by_the_entry_quarter():
    _, moved = aide.archive_insight_text(INBOX, "2026-08-01")
    assert sorted(moved) == ["2026-Q1", "2026-Q3"]


def test_archive_leaves_no_blank_gap_behind():
    text = "# I\n\n- [x] gap — a *(2026-01-01)*\n\n- [ ] gap — b *(2026-01-02)*\n"
    remaining, _ = aide.archive_insight_text(text, "2026-01-02")
    assert "\n\n\n" not in remaining
    assert remaining == "# I\n\n- [ ] gap — b *(2026-01-02)*\n"


def test_archive_of_nothing_is_a_no_op():
    remaining, moved = aide.archive_insight_text(INBOX, "2026-01-01")
    assert moved == {} and remaining == INBOX


def test_quarter_boundaries():
    assert aide.insight_quarter("2026-01-01") == "2026-Q1"
    assert aide.insight_quarter("2026-03-31") == "2026-Q1"
    assert aide.insight_quarter("2026-04-01") == "2026-Q2"
    assert aide.insight_quarter("2026-12-31") == "2026-Q4"


# --------------------------------------------------------------------------- #
# the command layer
# --------------------------------------------------------------------------- #
def test_list_prints_every_entry_with_its_number(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "1." in out and "4." in out
    assert "4 entries, 2 open" in out


def test_list_open_hides_the_closed_history(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list", "--open"]) == 0
    out = capsys.readouterr().out
    assert "insights.md has no verb" not in out
    assert "the reach check calls its own happy path a typo" in out
    assert "2 shown by the filters given" in out


def test_list_filters_by_type(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list", "--type", "gap"]) == 0
    out = capsys.readouterr().out
    assert "nothing exercises an installed engine" in out
    assert "utf-8-sig" not in out


def test_list_keeps_the_whole_provenance(tmp_path: Path, capsys):
    """Dropping the item ref sends the reader back to the file being replaced."""
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "*(item 117, 2026-03-04)*" in out
    assert "→ aide-loop #52" in out
    assert "*(2026-05-11)*" in out          # no item ref to invent


def test_list_renders_a_malformed_entry_verbatim(tmp_path: Path, capsys):
    """Its fields were never parsed, so none may be shown as if they had been."""
    repo = _repo(tmp_path, INBOX + "- [ ] nonsense\n")
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "    5. ?? - [ ] nonsense" in out


def test_list_rejects_an_unknown_type(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list", "--type", "bug"]) == 2


def test_list_omits_trails_unless_asked(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    assert "accepted into wave 3" not in capsys.readouterr().out
    assert aide.main(["--repo", str(repo), "insights", "list", "--trail"]) == 0
    assert "accepted into wave 3" in capsys.readouterr().out


def test_list_names_malformed_entries_without_hiding_them(tmp_path: Path, capsys):
    repo = _repo(tmp_path, INBOX + "- [ ] nonsense\n")
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "1 malformed" in out and "aide check" in out


def test_tick_writes_and_commits(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "tick", "2",
                      "--pointer", "item 121", "--date", "2026-08-24"]) == 0
    assert "*(2026-05-11)* → item 121" in _inbox(repo)
    log = _run(["git", "log", "-1", "--pretty=%s"], repo).stdout
    assert "triage insight 2" in log
    assert _run(["git", "status", "--porcelain"], repo).stdout.strip() == ""


def test_tick_no_commit_leaves_the_edit_uncommitted(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "tick", "2",
                      "--pointer", "item 121", "--no-commit"]) == 0
    assert "insights.md" in _run(["git", "status", "--porcelain"], repo).stdout


def test_tick_without_a_pointer_is_refused(tmp_path: Path):
    """A tick that records only 'triage happened' loses what triage decided."""
    repo = _repo(tmp_path)
    before = _inbox(repo)
    assert aide.main(["--repo", str(repo), "insights", "tick", "2", "--no-commit"]) == 2
    assert aide.main(["--repo", str(repo), "insights", "tick", "2",
                      "--pointer", "   ", "--no-commit"]) == 2
    assert _inbox(repo) == before


def test_tick_without_a_number_is_refused(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "tick",
                      "--pointer", "x", "--no-commit"]) == 2


def test_tick_of_a_missing_ordinal_exits_1_and_writes_nothing(tmp_path: Path):
    repo = _repo(tmp_path)
    before = _inbox(repo)
    assert aide.main(["--repo", str(repo), "insights", "tick", "99",
                      "--pointer", "x", "--no-commit"]) == 1
    assert _inbox(repo) == before


def test_archive_is_a_dry_run_by_default(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    before = _inbox(repo)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-06-01"]) == 0
    assert "dry run" in capsys.readouterr().out
    assert _inbox(repo) == before
    assert not (repo / "docs" / "aide" / "insights").exists()


def test_archive_yes_moves_entries_into_a_quarter_file(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-08-01", "--yes", "--no-commit"]) == 0
    q1 = (repo / "docs" / "aide" / "insights" / "archive-2026-Q1.md").read_text(encoding="utf-8")
    q3 = (repo / "docs" / "aide" / "insights" / "archive-2026-Q3.md").read_text(encoding="utf-8")
    assert q1.startswith("# Insight Archive — 2026-Q1")
    assert "insights.md has no verb" in q1
    assert "utf-8-sig" in q3
    live = _inbox(repo)
    assert len(aide.parse_insights(live)) == 2
    assert all(not e.ticked for e in aide.parse_insights(live))


def test_archive_says_the_numbers_have_shifted(tmp_path: Path, capsys):
    """A stale number from a pre-archive `list` is the one way to mis-tick."""
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-08-01", "--yes", "--no-commit"]) == 0
    assert "shifted" in capsys.readouterr().out


def test_archive_appends_to_an_existing_quarter_file(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-06-01", "--yes", "--no-commit"]) == 0
    inbox = repo / "docs" / "aide" / "insights.md"
    inbox.write_text(_inbox(repo) + "- [x] gap — later *(2026-02-02)* → x\n",
                     encoding="utf-8")
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-06-01", "--yes", "--no-commit"]) == 0
    q1 = (repo / "docs" / "aide" / "insights" / "archive-2026-Q1.md").read_text(encoding="utf-8")
    assert q1.count("# Insight Archive") == 1
    assert "insights.md has no verb" in q1 and "later" in q1


def test_archive_commits_both_sides_of_the_move(tmp_path: Path):
    repo = _repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-08-01", "--yes"]) == 0
    assert _run(["git", "status", "--porcelain"], repo).stdout.strip() == ""
    files = _run(["git", "show", "--name-only", "--pretty=", "HEAD"], repo).stdout
    assert "docs/aide/insights.md" in files
    assert "docs/aide/insights/archive-2026-Q1.md" in files


def test_archive_requires_a_well_formed_date(tmp_path: Path):
    repo = _repo(tmp_path)
    for bad in ([], ["--before", "2026-8-1"], ["--before", "yesterday"]):
        assert aide.main(["--repo", str(repo), "insights", "archive", *bad]) == 2


def test_a_missing_inbox_is_reported_not_crashed(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "docs" / "aide" / "insights.md").unlink()
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 2


# --------------------------------------------------------------------------- #
# the two scoping decisions this verb forced
# --------------------------------------------------------------------------- #
def test_archive_paths_are_always_authorised_for_scope():
    """`aide insights archive` is loop bookkeeping, like `aide progress set`."""
    authorised = aide.AuthorisedPaths(may_change=["core/scripts/aide.py"],
                                      asserts_against=[])
    always = tuple(f"docs/aide/{n}" for n in aide._ALWAYS_AUTHORISED)
    unauthorised, _ = aide.scope_findings(
        ["docs/aide/insights.md", "docs/aide/insights/archive-2026-Q3.md",
         "core/scripts/aide.py"], authorised, always)
    assert unauthorised == []


def test_the_archive_wildcard_cannot_reach_further_than_one_file_shape():
    """The one pattern in _ALWAYS_AUTHORISED must not be a subtree hole."""
    authorised = aide.AuthorisedPaths(may_change=[], asserts_against=[])
    always = tuple(f"docs/aide/{n}" for n in aide._ALWAYS_AUTHORISED)
    unauthorised, _ = aide.scope_findings(
        ["docs/aide/insights/archive-2026-Q3/leaked.md",
         "docs/aide/insights/notes.md",
         "docs/aide/items/042-x.md"], authorised, always)
    assert sorted(unauthorised) == ["docs/aide/insights/archive-2026-Q3/leaked.md",
                                    "docs/aide/insights/notes.md",
                                    "docs/aide/items/042-x.md"]


def test_an_archive_is_frozen_and_not_shape_checked(tmp_path: Path):
    """Warning on an immutable claim would name a defect no one may fix."""
    d = tmp_path / "docs" / "aide"
    (d / "insights").mkdir(parents=True)
    (d / "insights.md").write_text("# Insight Inbox\n", encoding="utf-8")
    (d / "insights" / "archive-2026-Q1.md").write_text(
        "# Insight Archive — 2026-Q1\n\n- [x] this shape is long gone\n", encoding="utf-8")
    assert aide.insight_warnings(d) == []


def test_an_unfilled_slot_is_still_an_error_inside_an_archive(tmp_path: Path):
    """Frozen against shape warnings, not against a genuine template residue."""
    d = tmp_path / "docs" / "aide"
    (d / "insights").mkdir(parents=True)
    (d / "insights" / "archive-2026-Q1.md").write_text(
        "# Insight Archive\n\n- [x] gap — {{unfilled}} *(2026-01-01)*\n", encoding="utf-8")
    errors = aide.template_residue_errors(d)
    assert any("archive-2026-Q1.md" in e for e in errors)
