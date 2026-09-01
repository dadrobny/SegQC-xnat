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
    # Local, before the first commit: the index holds the bytes the files
    # have, whatever the runner's global `core.autocrlf` says (§6 — a test
    # that lost the global config mid-run saw every tracked file "modified").
    _run(["git", "config", "core.autocrlf", "false"], repo)
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
    remaining, moved, _undatable = aide.archive_insight_text(INBOX, "2026-06-01")
    assert list(moved) == ["2026-Q1"]
    assert len(aide.parse_insights(remaining)) == 3
    assert "insights.md has no verb" not in remaining


def test_archive_never_moves_an_open_entry_however_old():
    """The open backlog is the working set; archiving it hides what list exists for."""
    remaining, moved, _undatable = aide.archive_insight_text(INBOX, "2027-01-01")
    kept = aide.parse_insights(remaining)
    assert all(not e.ticked for e in kept)
    assert [e.date for e in kept] == ["2026-05-11", "2026-08-15"]
    assert sum(len(v) for v in moved.values()) == 3  # two entries + one trail line


def test_archive_carries_the_status_trail_with_its_entry():
    _, moved, _undatable = aide.archive_insight_text(INBOX, "2026-06-01")
    assert moved["2026-Q1"] == [
        "- [x] framework — insights.md has no verb *(item 117, 2026-03-04)* → aide-loop #52",
        "  - **2026-03-05** → accepted into wave 3",
    ]


def test_archive_moves_lines_byte_for_byte():
    original = INBOX.splitlines()
    _, moved, _undatable = aide.archive_insight_text(INBOX, "2026-08-01")
    for lines in moved.values():
        for line in lines:
            assert line in original


def test_archive_groups_by_the_entry_quarter():
    _, moved, _undatable = aide.archive_insight_text(INBOX, "2026-08-01")
    assert sorted(moved) == ["2026-Q1", "2026-Q3"]


def test_archive_leaves_no_blank_gap_behind():
    text = "# I\n\n- [x] gap — a *(2026-01-01)*\n\n- [ ] gap — b *(2026-01-02)*\n"
    remaining, _, _undatable = aide.archive_insight_text(text, "2026-01-02")
    assert "\n\n\n" not in remaining
    assert remaining == "# I\n\n- [ ] gap — b *(2026-01-02)*\n"


def test_archive_of_nothing_is_a_no_op():
    remaining, moved, _undatable = aide.archive_insight_text(INBOX, "2026-01-01")
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
    assert aide.main(["--repo", str(repo), "insights", "tick", "1",
                      "--pointer", "x"]) == 2


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


# --------------------------------------------------------------------------- #
# provenance — what may stand between "*(" and the date (issue #76)
#
# The reported failure: the shape accepted `item NNN` alone, so two provenances
# the loop produces routinely — `queue-NNN` from planning done before any item
# exists, and `items NNN-NNN` from a finding spanning several — warned forever
# AND could not be archived, because the same pattern is what yields the date
# `archive --before` cuts on. Neither was fixable in place: §1 makes the claim
# immutable, and collapsing a range to one item destroys the provenance the
# marker records. The date is now the only load-bearing part.
# --------------------------------------------------------------------------- #
WIDE = """\
# Insight Inbox

_Entries below, newest last._

- [x] gap — queue planning found no home for this *(queue-014, 2026-07-26)*
- [x] defect — the three specs disagree on the same path *(items 099-101, 2026-07-27)*
- [x] knowledge — provenance can be anything honest *(the 2026 offsite, 2026-07-28)*
- [ ] framework — a bare date is still fine *(2026-07-29)*
"""


def test_a_queue_or_range_provenance_parses_and_keeps_its_date():
    """The date is what `archive` cuts on, so every accepted form must yield one."""
    entries = aide.parse_insights(WIDE)
    assert [e.date for e in entries] == [
        "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29"]
    assert [e.source for e in entries] == [
        "queue-014", "items 099-101", "the 2026 offsite", None]


def test_only_a_single_item_provenance_yields_an_item_number():
    """A range and a queue name no one item; inventing one would be a guess."""
    assert [e.item for e in aide.parse_insights(WIDE)] == [None, None, None, None]
    assert aide.parse_insights(
        "- [ ] gap — x *(item 099, 2026-07-26)*\n")[0].item == 99


def test_the_claim_survives_a_widened_provenance():
    """Text is still cut at the provenance, not at the first parenthesis."""
    entries = aide.parse_insights(WIDE)
    assert entries[1].text == "the three specs disagree on the same path"
    assert entries[0].ticked is True and entries[3].ticked is False


def test_check_no_longer_warns_on_a_queue_or_multi_item_capture(tmp_path: Path):
    """The reported entries, verbatim: three permanent warnings, now none."""
    d = tmp_path / "docs" / "aide"
    d.mkdir(parents=True)
    (d / "insights.md").write_text(WIDE, encoding="utf-8")
    assert aide.insight_warnings(d) == []


def test_the_date_stays_strict_where_the_provenance_relaxed(tmp_path: Path):
    """Relaxing the slug must not relax the one field every verb depends on."""
    d = tmp_path / "docs" / "aide"
    d.mkdir(parents=True)
    (d / "insights.md").write_text(
        "# I\n\n"
        "- [ ] gap — no date at all *(queue-014)*\n"
        "- [ ] gap — not ISO *(item 099, 26-07-26)*\n"
        "- [ ] gap — a provenance may not span lines *(queue-014,\n"
        "- [ ] nonsense — not a known type *(2026-07-26)*\n",
        encoding="utf-8")
    warnings = aide.insight_warnings(d)
    assert len(warnings) == 4
    assert all("YYYY-MM-DD" in w for w in warnings)


def test_archive_moves_a_queue_or_multi_item_entry():
    """The half of #76 that outlived the warning: pinned in the live file forever."""
    remaining, moved, undatable = aide.archive_insight_text(WIDE, "2026-08-01")
    assert sum(len(v) for v in moved.values()) == 3
    assert undatable == []
    kept = aide.parse_insights(remaining)
    assert [e.text.strip() for e in kept] == ["a bare date is still fine"]


def test_list_reprints_a_range_or_queue_provenance_verbatim(tmp_path: Path, capsys):
    """Re-deriving the provenance from an item number can print back only one form."""
    repo = _repo(tmp_path, WIDE)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "*(queue-014, 2026-07-26)*" in out
    assert "*(items 099-101, 2026-07-27)*" in out
    assert "*(2026-07-29)*" in out


def test_tick_works_on_a_widened_provenance(tmp_path: Path):
    """`tick` refuses what does not parse, so widening must reach it too."""
    repo = _repo(tmp_path, WIDE.replace("- [x] gap —", "- [ ] gap —", 1))
    assert aide.main(["--repo", str(repo), "insights", "tick", "1",
                      "--pointer", "aide-loop #76"]) == 0
    assert "*(queue-014, 2026-07-26)* → aide-loop #76" in _inbox(repo)


# --------------------------------------------------------------------------- #
# an entry no cut can reach is reported, not silently skipped (issue #76)
# --------------------------------------------------------------------------- #
UNDATABLE = """\
# Insight Inbox

- [x] gap — dated and closed *(2026-01-01)*
- [x] this one never parsed at all
"""


def test_archive_returns_the_closed_entries_it_could_not_date():
    _, _, undatable = aide.archive_insight_text(UNDATABLE, "2026-06-01")
    assert [e.ordinal for e in undatable] == [2]


def test_an_open_undated_entry_is_not_reported_as_unarchivable():
    """An open entry never moves anyway; naming it would be noise, not a finding."""
    _, _, undatable = aide.archive_insight_text(
        UNDATABLE.replace("- [x] this one", "- [ ] this one"), "2026-06-01")
    assert undatable == []


def test_archive_names_the_entry_it_had_to_leave_behind(tmp_path: Path, capsys):
    repo = _repo(tmp_path, UNDATABLE)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2026-06-01"]) == 0
    err = capsys.readouterr().err
    assert "entry 2" in err and "insights.md:4" in err
    assert "1 closed entry could not be dated" in err


def test_the_report_survives_a_run_where_nothing_moved(tmp_path: Path, capsys):
    """The run that most needs it: the live file will not shrink and says why."""
    repo = _repo(tmp_path, UNDATABLE)
    assert aide.main(["--repo", str(repo), "insights", "archive",
                      "--before", "2020-01-01"]) == 0
    captured = capsys.readouterr()
    assert "nothing closed before 2020-01-01" in captured.out
    assert "could not be dated" in captured.err


# --------------------------------------------------------------------------- #
# which marker is the provenance, when a line carries more than one
#
# A free-form provenance means an aside inside the claim can wear the marker's
# shape. Position alone cannot decide it: the first match takes the claim's
# aside, the last takes the pointer's. The rule is the marker that leaves a
# well-formed tail — nothing, or the `→` pointer.
# --------------------------------------------------------------------------- #
def test_an_aside_inside_the_claim_does_not_steal_the_provenance():
    """Taking the aside's date would file the entry in the wrong quarter, silently."""
    line = ("- [ ] defect — config default is *(prod, 2020-01-01)* not "
            "*(item 099, 2026-07-26)*\n")
    e = aide.parse_insights(line)[0]
    assert (e.source, e.date, e.item) == ("item 099", "2026-07-26", 99)
    assert e.text == "config default is *(prod, 2020-01-01)* not"


def test_an_aside_inside_the_pointer_does_not_steal_it_either():
    """The symmetric case, which taking the *last* marker would get wrong."""
    line = "- [x] gap — a *(item 099, 2026-07-26)* → see *(note, 2026-08-01)*\n"
    e = aide.parse_insights(line)[0]
    assert (e.source, e.date) == ("item 099", "2026-07-26")
    assert e.pointer == "see *(note, 2026-08-01)*"


def test_an_aside_that_would_be_archived_to_the_wrong_quarter_is_not():
    """The consequence the parse rule exists to prevent, through the verb itself."""
    text = ("- [x] defect — was *(prod, 2020-01-01)* now *(item 099, 2026-07-26)*\n")
    _, moved, _u = aide.archive_insight_text(text, "2026-08-01")
    assert list(moved) == ["2026-Q3"]          # not 2020-Q1


def test_a_hand_written_tail_still_parses_as_it_always_did():
    """Entries predating `tick` carry tails that are neither empty nor a pointer."""
    e = aide.parse_insights("- [x] gap — a *(2026-01-01)* — landed in X\n")[0]
    assert (e.date, e.pointer) == ("2026-01-01", None)


def test_a_blank_provenance_is_still_a_shape_warning(tmp_path: Path):
    """Free-form is not empty: a stray comma says nothing and should be fixed."""
    d = tmp_path / "docs" / "aide"
    d.mkdir(parents=True)
    (d / "insights.md").write_text(
        "# I\n\n- [ ] gap — a stray comma *(   , 2026-01-01)*\n", encoding="utf-8")
    assert len(aide.insight_warnings(d)) == 1
    assert aide.parse_insights("- [ ] gap — a *(   , 2026-01-01)*\n")[0].date is None


def test_the_patterns_do_not_backtrack_catastrophically():
    """Both are run over every bullet in the file, malformed ones included."""
    import time
    evil = "- [ ] gap — " + "a(" * 4000 + " *(item 1, 2026-01-01)*"
    start = time.time()
    aide.parse_insights(evil)
    assert time.time() - start < 1.0


# --------------------------------------------------------------------------- #
# the engine version an insight was observed under (issue #97)
#
# The reported failure: an entry records where a finding came from and when,
# never *which engine it was seen on* — and the value is sitting on disk as
# `.aide/VERSION` at capture time. The date cannot proxy for it, so eight
# framework issues that landed upstream across an engine restructure could not
# be placed on either side of it, and every older-engine claim was re-verified
# by hand. The version is conventional, not grammatical: what the CLI must do
# is accept it, parse it, and print it back — never warn about it.
# --------------------------------------------------------------------------- #
VERSIONED = """\
# Insight Inbox

_Entries below, newest last._

- [ ] framework — the reach check has no engine version *(item 042, 2026-08-29, engine 1.22.0)*
- [x] defect — captured before the convention existed *(item 041, 2026-08-01)*
- [ ] knowledge — a bare date takes one too *(2026-08-29, engine 1.22.0)*
"""


def test_a_versioned_entry_passes_the_shape_check_clean(tmp_path: Path):
    """A warning on a captured line can never be cleared, so this is the
    load-bearing assertion of the pair: the new component must not produce
    permanent noise on a well-formed entry."""
    d = tmp_path / "docs" / "aide"
    d.mkdir(parents=True)
    (d / "insights.md").write_text(VERSIONED, encoding="utf-8")
    assert aide.insight_warnings(d) == []


def test_the_version_is_parsed_out_and_does_not_disturb_the_other_fields():
    """`note` is a field of its own; the date, provenance and item number are
    read exactly as they were before it existed."""
    entries = aide.parse_insights(VERSIONED)
    assert [e.note for e in entries] == ["engine 1.22.0", None, "engine 1.22.0"]
    assert [e.date for e in entries] == ["2026-08-29", "2026-08-01", "2026-08-29"]
    assert [e.source for e in entries] == ["item 042", "item 041", None]
    assert [e.item for e in entries] == [42, 41, None]
    assert entries[0].text == "the reach check has no engine version"


def test_the_version_is_free_form_not_a_grammar():
    """Enumerating the accepted spelling would reject an honest capture
    permanently — the claim line is immutable. Same argument as the provenance
    (issue #76), and sharper here, since entries predate the convention."""
    e = aide.parse_insights(
        "- [ ] gap — a *(item 1, 2026-01-01, engine 1.22.0-rc1 on windows)*\n")[0]
    assert (e.date, e.note) == ("2026-01-01", "engine 1.22.0-rc1 on windows")


def test_an_entry_captured_without_a_version_is_untouched():
    """The convention is never retrofitted, so the un-versioned entry must keep
    parsing exactly as it did — `note` is None, not an invented value."""
    entries = aide.parse_insights(INBOX)
    assert [e.note for e in entries] == [None, None, None, None]


def test_list_reprints_the_engine_version(tmp_path: Path, capsys):
    """Triage reads the listing, not the file (the feedback-loop skill says so),
    so a version the listing drops is a version triage cannot carry into the
    issue it files."""
    repo = _repo(tmp_path, VERSIONED)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    out = capsys.readouterr().out
    assert "*(item 042, 2026-08-29, engine 1.22.0)*" in out
    assert "*(2026-08-29, engine 1.22.0)*" in out
    assert "*(item 041, 2026-08-01)*" in out


def test_tick_and_archive_reach_a_versioned_entry(tmp_path: Path):
    """The date is still what `archive` cuts on, and `tick` still refuses only
    what does not parse — widening the marker must cost neither verb its entry."""
    repo = _repo(tmp_path, VERSIONED)
    assert aide.main(["--repo", str(repo), "insights", "tick", "1",
                      "--pointer", "aide-loop #97"]) == 0
    assert ("*(item 042, 2026-08-29, engine 1.22.0)* → aide-loop #97"
            in _inbox(repo))
    _, moved, undatable = aide.archive_insight_text(VERSIONED, "2026-08-15")
    assert list(moved) == ["2026-Q3"] and undatable == []


def test_the_date_stays_strict_with_a_version_after_it(tmp_path: Path):
    """The one field every verb depends on did not relax on its right either."""
    d = tmp_path / "docs" / "aide"
    d.mkdir(parents=True)
    (d / "insights.md").write_text(
        "# I\n\n"
        "- [ ] gap — no date, only a version *(item 1, engine 1.22.0)*\n"
        "- [ ] gap — not ISO *(item 1, 26-08-29, engine 1.22.0)*\n"
        "- [ ] gap — an empty trailer says nothing *(item 1, 2026-08-29,  )*\n",
        encoding="utf-8")
    assert len(aide.insight_warnings(d)) == 3


# --------------------------------------------------------------------------- #
# the engine guarantees the inbox exists (issue #85)
# --------------------------------------------------------------------------- #
_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "insights.md"

#: The least progress.md `check` passes on, so the verb reaches its exit code
#: for the document set's own reasons and not for a fixture's.
_PROGRESS = "# P\n\n| 1 | S | G | 📋 |\n\n| G1 | O | 📋 |\n\n## Stage 1 — S — 📋\n"


def _loop_repo_without_inbox(tmp_path: Path) -> Path:
    repo = _repo(tmp_path)
    (repo / "docs" / "aide" / "progress.md").write_text(_PROGRESS, encoding="utf-8")
    (repo / "docs" / "aide" / "insights.md").unlink()
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "a document set with no inbox yet"], repo)
    return repo


def _cli_only_repo(tmp_path: Path) -> Path:
    """A repo that adopted the CLI and not the loop: aide.toml, no docs_dir."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    return repo


def _clean(repo: Path) -> bool:
    return _run(["git", "status", "--porcelain"], repo).stdout.strip() == ""


def _status(repo: Path) -> list:
    return _run(["git", "status", "--porcelain"], repo).stdout.splitlines()


def _staged(repo: Path) -> list:
    return _run(["git", "diff", "--cached", "--name-only"], repo).stdout.split()


def _assert_untracked_only(repo: Path, rel: str = "docs/aide/insights.md") -> None:
    """*rel* is untracked and nothing at all is staged — asserted on the file's
    own status line, not on the whole porcelain list, which may carry lines
    that are the runner's business (line endings) and not this test's."""
    status = _status(repo)
    assert f"?? {rel}" in status, status
    assert _staged(repo) == [], _staged(repo)


def _files_in_head(repo: Path) -> list:
    """What HEAD's commit touches — posix paths, one per line as git prints
    them (never whitespace-split: a path may carry a space)."""
    out = _run(["git", "-c", "core.quotepath=false", "show", "--name-only",
                "--format=", "HEAD"], repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _head(repo: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()


def _without_git_identity(repo: Path, monkeypatch, tmp_path: Path) -> None:
    """A fresh clone before `git config user.name`: the commit is refused."""
    for key in ("user.name", "user.email"):
        _run(["git", "config", "--unset", key], repo)
    nowhere = tmp_path / "no-such-gitconfig"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(nowhere))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(nowhere))
    monkeypatch.setenv("HOME", str(tmp_path / "no-such-home"))
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)


def test_the_template_is_where_the_engine_looks_for_it():
    """Every test below compares against this file; if the layout moves, this
    is the one that fails with a reason instead of the rest with a mystery."""
    assert _TEMPLATE.is_file()
    assert aide._TEMPLATES_DIR == _TEMPLATE.parent
    assert b"insight" in _TEMPLATE.read_bytes().lower()


def test_check_creates_a_missing_inbox_byte_for_byte(tmp_path: Path):
    repo = _loop_repo_without_inbox(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert (repo / "docs" / "aide" / "insights.md").read_bytes() == _TEMPLATE.read_bytes()


def test_check_commits_the_inbox_it_created_and_nothing_else(tmp_path: Path):
    """`aide sync` refuses a dirty tree; a creation left untracked would stall
    the next preflight of the loop it exists to serve. The commit's CONTENTS
    are the assertion — "a commit happened" and "tree clean" were both true
    of a commit that had swept a builder's staged work in with the inbox."""
    repo = _loop_repo_without_inbox(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert _clean(repo)
    subject = _run(["git", "log", "-1", "--format=%s"], repo).stdout.strip()
    assert subject.startswith("docs(aide):")
    assert _files_in_head(repo) == ["docs/aide/insights.md"]


def test_the_inbox_commit_leaves_staged_work_staged_and_out_of_it(tmp_path: Path):
    repo = _loop_repo_without_inbox(tmp_path)
    (repo / "feature.py").write_text("x = 1\n", encoding="utf-8")
    _run(["git", "add", "feature.py"], repo)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert _files_in_head(repo) == ["docs/aide/insights.md"]
    assert _staged(repo) == ["feature.py"]
    assert not any("insights.md" in line for line in _status(repo))


def test_a_commit_git_refuses_leaves_the_inbox_untracked_not_staged(
        tmp_path: Path, monkeypatch, capsys):
    """A staged-but-uncommitted inbox stalls `aide sync` exactly as an
    untracked one does, with no message saying why. Untracked, plus a notice
    that names the refusal, is the honest degradation."""
    repo = _loop_repo_without_inbox(tmp_path)
    before = _head(repo)
    _without_git_identity(repo, monkeypatch, tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert _head(repo) == before
    _assert_untracked_only(repo)
    out = capsys.readouterr().out
    notice = [l for l in out.splitlines() if l.startswith("notice:")]
    assert len(notice) == 1 and "NOT committed" in notice[0]


def test_git_off_path_degrades_to_created_not_committed(
        tmp_path: Path, monkeypatch, capsys):
    """`check` ran in a repo with no usable `git` before 1.26.0 and must still:
    the creation happens, the commit is a reason in the notice, no traceback."""
    repo = _loop_repo_without_inbox(tmp_path)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert (repo / "docs" / "aide" / "insights.md").read_bytes() == _TEMPLATE.read_bytes()
    notice = [l for l in capsys.readouterr().out.splitlines() if l.startswith("notice:")]
    assert len(notice) == 1 and "NOT committed" in notice[0]
    monkeypatch.undo()
    _assert_untracked_only(repo)


def test_a_detached_head_gets_the_file_and_no_dangling_commit(
        tmp_path: Path, monkeypatch, capsys):
    repo = _loop_repo_without_inbox(tmp_path)
    before = _head(repo)
    _run(["git", "checkout", "--quiet", "--detach"], repo)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert _head(repo) == before
    _assert_untracked_only(repo)
    notice = [l for l in capsys.readouterr().out.splitlines() if l.startswith("notice:")]
    assert len(notice) == 1 and "detached" in notice[0]


def test_check_says_it_created_the_inbox(tmp_path: Path, capsys):
    repo = _loop_repo_without_inbox(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    out = capsys.readouterr().out
    notice = [l for l in out.splitlines() if l.startswith("notice:")]
    assert len(notice) == 1 and "docs/aide/insights.md" in notice[0]
    assert "aide check: OK" in out


def test_check_is_silent_about_the_inbox_once_it_exists(tmp_path: Path, capsys):
    repo = _loop_repo_without_inbox(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    capsys.readouterr()
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert "notice:" not in capsys.readouterr().out


def test_check_never_overwrites_an_existing_inbox_even_a_malformed_one(tmp_path: Path):
    repo = _loop_repo_without_inbox(tmp_path)
    inbox = repo / "docs" / "aide" / "insights.md"
    inbox.write_bytes(b"- [ ] not a shape the parser knows\n")
    assert aide.main(["--repo", str(repo), "check"]) == 0  # a shape *warning*
    assert inbox.read_bytes() == b"- [ ] not a shape the parser knows\n"


def test_check_creates_nothing_in_a_repo_with_no_document_set(tmp_path: Path):
    repo = _cli_only_repo(tmp_path)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert not (repo / "docs").exists()


def test_the_helper_reports_what_it_did(tmp_path: Path):
    repo = _loop_repo_without_inbox(tmp_path)
    config = aide.load_config(repo)
    created = aide.ensure_insights_inbox(repo, config, verb="test")
    assert created == repo / "docs" / "aide" / "insights.md"
    assert aide.ensure_insights_inbox(repo, config, verb="test") is None
    assert aide.ensure_insights_inbox(_cli_only_repo(tmp_path / "other"),
                                      config, verb="test") is None


def test_a_missing_template_is_reported_not_crashed(tmp_path: Path, monkeypatch, capsys):
    """An install that lost `.aide/templates/` is incomplete, not broken here:
    the gate still runs, still exits on the document set's merits, and says
    which file it could not create and why."""
    repo = _loop_repo_without_inbox(tmp_path)
    monkeypatch.setattr(aide, "_TEMPLATES_DIR", tmp_path / "nowhere")
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert not (repo / "docs" / "aide" / "insights.md").exists()
    err = capsys.readouterr().err
    assert "insights.md" in err and "install" in err


def test_list_on_a_missing_inbox_creates_it_and_reports_an_empty_backlog(
        tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    inbox = repo / "docs" / "aide" / "insights.md"
    inbox.unlink()
    _run(["git", "commit", "-am", "drop the inbox"], repo)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 0
    assert inbox.read_bytes() == _TEMPLATE.read_bytes()
    assert _clean(repo)
    out = capsys.readouterr().out
    assert "notice:" in out and "0 entries, 0 open" in out


def test_list_no_commit_leaves_the_created_inbox_uncommitted(tmp_path: Path):
    repo = _repo(tmp_path)
    inbox = repo / "docs" / "aide" / "insights.md"
    inbox.unlink()
    _run(["git", "commit", "-am", "drop the inbox"], repo)
    assert aide.main(["--repo", str(repo), "insights", "list", "--no-commit"]) == 0
    assert inbox.is_file() and not _clean(repo)


def test_list_with_no_document_set_creates_nothing(tmp_path: Path):
    repo = _cli_only_repo(tmp_path)
    assert aide.main(["--repo", str(repo), "insights", "list"]) == 2
    assert not (repo / "docs").exists()


def test_tick_and_archive_on_a_missing_inbox_point_at_check(tmp_path: Path, capsys):
    """Neither can act on a file that is not there, and the way to get one is
    a verb now — not the hand copy the old message prescribed."""
    repo = _repo(tmp_path)
    (repo / "docs" / "aide" / "insights.md").unlink()
    for verb in (["tick", "1", "--pointer", "x"], ["archive", "--before", "2026-01-01"]):
        assert aide.main(["--repo", str(repo), "insights", *verb]) == 2
        err = capsys.readouterr().err
        assert "aide check" in err and "templates" not in err
    assert not (repo / "docs" / "aide" / "insights.md").exists()


def test_a_docs_dir_with_a_space_is_recognised_in_its_own_commit(
        tmp_path: Path, capsys):
    """The committed-path check tokenised `git show` output on whitespace, so
    `my docs/aide/insights.md` never matched itself and the notice said "NOT
    committed" about a file that was in the commit."""
    repo = _repo(tmp_path)
    ddir = repo / "my docs" / "aide"
    ddir.mkdir(parents=True)
    (ddir / "progress.md").write_text(_PROGRESS, encoding="utf-8")
    toml = AIDE_TOML.replace('docs_dir = "docs/aide"', 'docs_dir = "my docs/aide"')
    assert "my docs" in toml  # the substitution took
    (repo / "aide.toml").write_text(toml, encoding="utf-8")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "a docs_dir with a space"], repo)
    assert aide.main(["--repo", str(repo), "check"]) == 0
    inbox = ddir / "insights.md"
    assert inbox.read_bytes() == _TEMPLATE.read_bytes()
    assert _files_in_head(repo) == [inbox.relative_to(repo).as_posix()]
    notice = [l for l in capsys.readouterr().out.splitlines() if l.startswith("notice:")]
    assert len(notice) == 1 and "and committed it" in notice[0]


def test_the_shared_committer_is_loud_when_git_cannot_run(
        tmp_path: Path, monkeypatch, capsys):
    """`progress set`, `tick` and `archive` discard the committer's return, so
    the reason must reach stderr from the committer itself — or `tick` prints
    its success line over an edit that was never committed."""
    repo = _repo(tmp_path)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    why = aide._commit_docs_files(repo, aide.load_config(repo), "m",
                                  ["docs/aide/insights.md"])
    assert why and "git could not be run" in why
    assert "could not commit docs/aide/insights.md" in capsys.readouterr().err
    assert aide.main(["--repo", str(repo), "insights", "tick", "2",
                      "--pointer", "item 003"]) == 0
    err = capsys.readouterr().err
    assert "could not commit docs/aide/insights.md" in err and "Traceback" not in err
    monkeypatch.undo()
    assert "- [x] defect" in _inbox(repo)  # the edit landed ...
    assert " M docs/aide/insights.md" in _status(repo)  # ... and is uncommitted
    assert _staged(repo) == []
