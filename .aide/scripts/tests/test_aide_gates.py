"""Tests for `## Human gates` — a decision only a person can make, blocking work.

Kept separate from acceptance boxes deliberately: conventions.md §1 defines
those as observable checks *of the built thing*, which a steering decision is
not. Same reasoning that gave Outcome targets their own table.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_gates", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _progress(rows: str, stage_status: str = "🚧") -> str:
    return f"""\
# Demo — Progress

## Stage summary

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 1 | Rules | G1 | {stage_status} |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Rules | Stage 1 | {stage_status} |

## Human gates

| Gate | Blocks | Status | Decision / evidence |
|------|--------|--------|---------------------|
{rows}

## Stage 1 — Rules — {stage_status}

**Deliverables.**
- 📋 A. *(Item 027)*
- 📋 B. *(Item 028)*

**Acceptance.**
- [ ] Rules fire.
"""


AWAITING = "| Golden retirement approved | 028 | ⏳ Awaiting | — |"
APPROVED = "| Golden retirement approved | 028 | ✅ Approved (2026-08-18) | ok |"
ALL = "| Real segmenter output arrived | all | ⏳ Awaiting | — |"
STAGE = "| Stage-1 direction approved | stage 1 | ⏳ Awaiting | — |"


def _lines(rows: str):
    return _progress(rows).splitlines()


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def test_parses_a_gate_row():
    g = aide.human_gates(_lines(AWAITING))[0]
    assert g.text == "Golden retirement approved"
    assert g.blocks == [28] and g.blocks_all is False and g.kind == "awaiting"


def test_bare_numbers_in_blocks_are_parsed():
    """A column headed "Blocks" invites bare numbers. The shared extractor keys
    off the word "Item", so without normalisation this parses as nothing — and
    a gate blocking nothing is a gate that silently does not work."""
    rows = "| G | 106, 110–112 | ⏳ Awaiting | — |"
    assert aide.human_gates(_lines(rows))[0].blocks == [106, 110, 111, 112]


def test_item_reference_form_also_parsed():
    rows = "| G | Items 106, 108 | ⏳ Awaiting | — |"
    assert aide.human_gates(_lines(rows))[0].blocks == [106, 108]


def test_all_is_recognised():
    g = aide.human_gates(_lines(ALL))[0]
    assert g.blocks_all is True and g.blocks == [] and g.stage is None


def test_stage_reach_is_recognised():
    g = aide.human_gates(_lines(STAGE))[0]
    assert g.stage == "1" and g.blocks == [] and g.blocks_all is False


def test_stage_reach_resolves_through_progress_deliverables():
    """A stage gate follows the roadmap: its reach is whatever items that
    stage's deliverables reference, now — not a list frozen when it was
    written, and not whichever queue happens to be live."""
    blocked, everything = aide.gate_blocked_items(_lines(STAGE))
    assert blocked == {27, 28} and everything == []


def test_stage_reach_of_an_unknown_stage_holds_nothing():
    rows = "| G | stage 99 | ⏳ Awaiting | — |"
    blocked, _ = aide.gate_blocked_items(_lines(rows))
    assert blocked == set()


def test_no_table_is_no_gates():
    text = _progress(AWAITING).replace("## Human gates", "## Something else")
    assert aide.human_gates(text.splitlines()) == []


def test_header_and_separator_rows_are_skipped():
    assert len(aide.human_gates(_lines(AWAITING))) == 1


def test_table_ends_at_the_next_heading():
    """A deliverable bullet after the table must not be read as a gate row."""
    assert len(aide.human_gates(_lines(f"{AWAITING}\n{ALL}"))) == 2


# --------------------------------------------------------------------------- #
# resolution semantics
# --------------------------------------------------------------------------- #
def test_approved_gate_is_resolved():
    assert aide.blocking_gates(_lines(APPROVED)) == []


def test_declined_keeps_blocking():
    """A refusal is *resolved* — a person decided — but the decision was "no",
    so releasing the work would run exactly what was refused. Only approval
    opens a gate; the remedy for a decline is to re-plan."""
    rows = "| G | 028 | ❌ Declined (2026-08-18) | keep v0 |"
    pending = aide.blocking_gates(_lines(rows))
    assert len(pending) == 1 and pending[0].kind == "declined"
    blocked, _ = aide.gate_blocked_items(_lines(rows))
    assert blocked == {28}


def test_declined_warning_says_it_still_blocks():
    rows = "| G | 028 | ❌ Declined (2026-08-18) | keep v0 |"
    w = aide.gate_warnings(_lines(rows))[0]
    assert "DECLINED" in w and "still blocks" in w


def test_unrecognised_status_stays_unresolved():
    """A typo in the mark must not silently open a gate."""
    rows = "| G | 028 | approved-ish | — |"
    pending = aide.blocking_gates(_lines(rows))
    assert len(pending) == 1 and pending[0].kind is None


def test_gate_blocked_items_splits_named_from_block_everything():
    blocked, everything = aide.gate_blocked_items(_lines(f"{AWAITING}\n{ALL}"))
    assert blocked == {28}
    assert len(everything) == 1


def test_approved_gate_blocks_nothing():
    blocked, everything = aide.gate_blocked_items(_lines(APPROVED))
    assert blocked == set() and everything == []


# --------------------------------------------------------------------------- #
# warnings
# --------------------------------------------------------------------------- #
def test_awaiting_gate_warns_with_its_reach():
    w = aide.gate_warnings(_lines(AWAITING))
    assert len(w) == 1 and "items 028" in w[0]


def test_all_warning_says_all_items():
    assert "all items" in aide.gate_warnings(_lines(ALL))[0]


def test_stage_warning_names_the_stage():
    assert "stage 1" in aide.gate_warnings(_lines(STAGE))[0]


def test_unrecognised_status_warns_about_the_vocabulary():
    rows = "| G | 028 | approved-ish | — |"
    assert "unrecognised status" in aide.gate_warnings(_lines(rows))[0]


def test_resolved_gates_are_silent():
    assert aide.gate_warnings(_lines(APPROVED)) == []


def test_gate_naming_nothing_is_called_out():
    """A gate that blocks nothing is inert; say so rather than look busy."""
    rows = "| G | — | ⏳ Awaiting | — |"
    assert "nothing named" in aide.gate_warnings(_lines(rows))[0]


def test_stage_warning_resolves_how_much_the_gate_holds():
    """The reach is computed at check time either way; throwing it away made a
    mis-scoped `stage N` gate invisible until a runner stalled on it — the
    observed case held the very item meant to produce the gate's evidence."""
    w = aide.gate_warnings(_lines(STAGE))[0]
    assert "holding 2 item(s): 027, 028" in w


def test_declined_stage_warning_also_resolves_the_reach():
    rows = "| G | stage 1 | ❌ Declined (2026-08-18) | keep v0 |"
    w = aide.gate_warnings(_lines(rows))[0]
    assert "still blocks" in w and "holding 2 item(s): 027, 028" in w


def test_item_list_warning_needs_no_resolution():
    """An item-list reach already names its items; no breadth suffix is added."""
    w = aide.gate_warnings(_lines(AWAITING))[0]
    assert "items 028" in w and "holding" not in w


def test_breadth_counts_only_items_the_gate_still_holds():
    """A ✅ item has merged and a ❌ one is out — 'holding' either would
    overstate the reach against the enforcement the message mirrors (claim
    blocks neither)."""
    lines = _progress(STAGE).replace("- 📋 A. *(Item 027)*",
                                     "- ✅ A. *(Item 027)*").splitlines()
    w = aide.gate_warnings(lines)[0]
    assert "holding 1 item(s): 028" in w and "027" not in w


def test_breadth_of_an_all_merged_stage_falls_back_to_the_bare_reach():
    lines = _progress(STAGE).replace("📋", "✅").splitlines()
    w = next(x for x in aide.gate_warnings(lines) if "awaiting" in x)
    assert "stage 1" in w and "holding" not in w


# --------------------------------------------------------------------------- #
# set_gate_status
# --------------------------------------------------------------------------- #
def test_approve_writes_mark_date_and_note():
    out = aide.set_gate_status(_progress(AWAITING), 1, "approved",
                               "reviewed with maintainer", today="2026-08-18")
    row = next(l for l in out.splitlines() if "Golden retirement" in l and "|" in l)
    assert "✅ Approved (2026-08-18)" in row
    assert "reviewed with maintainer" in row
    assert aide.blocking_gates(out.splitlines()) == []


def test_decline_is_recorded_distinctly():
    out = aide.set_gate_status(_progress(AWAITING), 1, "declined", "not now",
                               today="2026-08-18")
    assert "❌ Declined (2026-08-18)" in out
    assert aide.human_gates(out.splitlines())[0].kind == "declined"


def test_out_of_range_index_raises():
    import pytest
    with pytest.raises(ValueError, match="out of range"):
        aide.set_gate_status(_progress(AWAITING), 5, "approved")


def test_missing_table_raises():
    import pytest
    text = _progress(AWAITING).replace("## Human gates", "## Other")
    with pytest.raises(ValueError, match="no '## Human gates' table"):
        aide.set_gate_status(text, 1, "approved")


def test_other_rows_are_untouched():
    out = aide.set_gate_status(_progress(f"{AWAITING}\n{ALL}"), 1, "approved",
                               today="2026-08-18")
    gates = aide.human_gates(out.splitlines())
    assert gates[0].kind == "approved"
    assert gates[1].kind == "awaiting" and gates[1].blocks_all is True


def test_gate_table_does_not_disturb_the_stage_rollup():
    """The gates table sits in progress.md beside the tables the rollup reads;
    it must not be mistaken for one of them."""
    text = _progress(AWAITING)
    statuses = aide._parse_item_status(text.splitlines())[2]
    assert statuses.get(27) == "planned" and statuses.get(28) == "planned"


# --------------------------------------------------------------------------- #
# end to end — claim refuses, gate verb resolves, claim proceeds
# --------------------------------------------------------------------------- #
AIDE_TOML = '[project]\nname = "Demo"\ndocs_dir = "docs/aide"\n\n[git]\nmode = "local"\nmain_branch = "main"\nbranch_prefix = "aide/"\n'
QUEUE = "# Demo — Work Queue 003\n\n### Item 027: Alpha\nA.\n\n### Item 028: Beta\nB.\n"


def _run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding="utf-8")


def _repo(tmp_path: Path, rows: str) -> Path:
    repo = tmp_path / "repo"
    d = repo / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (repo / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    (d / "progress.md").write_text(_progress(rows), encoding="utf-8")
    (d / "queue" / "queue-003.md").write_text(QUEUE, encoding="utf-8")
    _run(["git", "init", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@e.com"], repo)
    _run(["git", "config", "user.name", "T"], repo)
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "init"], repo)
    return repo


def test_claim_skips_a_gated_item_and_offers_the_next(tmp_path: Path, capsys):
    """Item-scoped by default: the queue keeps producing work. Only the items
    a gate names wait for it."""
    repo = _repo(tmp_path, AWAITING)          # blocks 028 only
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    assert "item 027" in capsys.readouterr().out


def test_all_gate_stops_everything(tmp_path: Path, capsys):
    """A decision that could invalidate downstream work must not have the loop
    racing ahead of it."""
    repo = _repo(tmp_path, ALL)
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "held by an unresolved human gate" in out
    assert "blocks everything" in out
    assert "item 027" not in out


def test_gate_list_numbers_the_rows(tmp_path: Path, capsys):
    repo = _repo(tmp_path, f"{AWAITING}\n{ALL}")
    assert aide.main(["--repo", str(repo), "gate", "list"]) == 0
    out = capsys.readouterr().out
    assert "1. ⏳" in out and "2. ⏳" in out
    assert "2 gate(s), 2 still blocking" in out


def test_approving_an_all_gate_releases_the_queue(tmp_path: Path, capsys):
    repo = _repo(tmp_path, ALL)
    assert aide.main(["--repo", str(repo), "gate", "approve", "1",
                      "--evidence", "data landed", "--no-commit"]) == 0
    capsys.readouterr()
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    assert "item 027" in capsys.readouterr().out


def test_gate_check_reports_the_outstanding_gate(tmp_path: Path):
    repo = _repo(tmp_path, AWAITING)
    _, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert any("awaiting a decision" in w for w in warnings)


def test_gate_out_of_range_is_an_error_not_a_noop(tmp_path: Path, capsys):
    repo = _repo(tmp_path, AWAITING)
    assert aide.main(["--repo", str(repo), "gate", "approve", "9", "--no-commit"]) == 2
    assert "out of range" in capsys.readouterr().err


def test_a_queue_branch_does_not_make_an_item_unclaimable(tmp_path: Path, capsys):
    """`aide/queue-027` is a queue branch, not a claim on item 027. The old
    unanchored search read the trailing digits as an item number and marked it
    permanently claimed — the 1.5.0 bug class, at the one call site that sweep
    missed."""
    repo = _repo(tmp_path, "| G | 999 | ⏳ Awaiting | — |")   # gate blocks nothing real
    _run(["git", "switch", "-c", "aide/queue-027"], repo)
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    assert "item 027" in capsys.readouterr().out


def test_a_real_claim_branch_still_marks_its_item_claimed(tmp_path: Path, capsys):
    repo = _repo(tmp_path, "| G | 999 | ⏳ Awaiting | — |")
    _run(["git", "switch", "-c", "aide/027-alpha"], repo)
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "item 028" in out and "item 027" not in out


def test_gate_approve_without_a_number_reports_rather_than_crashing(tmp_path: Path, capsys):
    repo = _repo(tmp_path, AWAITING)
    assert aide.main(["--repo", str(repo), "gate", "approve", "--no-commit"]) == 2
    assert "needs a gate number" in capsys.readouterr().err


def test_none_left_is_not_blamed_on_an_unrelated_gate(tmp_path: Path, capsys):
    """A gate holding items that are not in play is not why this run found no
    work. Blaming it is a false explanation — worse than none, and exactly the
    'true about one ground, read as true of the repo' failure gates exist to
    remove."""
    repo = _repo(tmp_path, "| Unrelated | 999 | ⏳ Awaiting | — |")
    # Both queue items already claimed, so the empty result has nothing to do
    # with the gate.
    _run(["git", "switch", "-c", "aide/027-alpha"], repo)
    _run(["git", "switch", "-c", "aide/028-beta"], repo)
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "none left" in out
    assert "human gate" not in out


def test_none_left_names_only_the_gates_that_apply(tmp_path: Path, capsys):
    repo = _repo(tmp_path, "| Unrelated | 999 | ⏳ Awaiting | — |\n"
                           "| Relevant | 027, 028 | ⏳ Awaiting | — |")
    assert aide.main(["--repo", str(repo), "claim", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Relevant" in out and "Unrelated" not in out
    assert "items 027, 028" in out


def test_a_note_containing_a_pipe_is_refused():
    """`|` would add a column; a wrong-arity row is skipped by the parser, so a
    still-blocking gate would silently disappear."""
    import pytest
    with pytest.raises(ValueError, match="may not contain"):
        aide.set_gate_status(_progress(AWAITING), 1, "approved", "a | b")


def test_a_malformed_row_warns_instead_of_vanishing():
    """The most dangerous failure this feature can have is a gate that stops
    being read: "a person must decide" silently becomes "nothing is blocking"."""
    rows = "| G | 028 | ⏳ Awaiting | note with | a pipe |"
    w = aide.gate_warnings(_lines(rows))
    assert any("being SKIPPED" in x for x in w)


def test_a_well_formed_table_produces_no_arity_warning():
    assert not any("columns, not 4" in w for w in aide.gate_warnings(_lines(AWAITING)))


def test_a_note_with_a_line_break_is_refused():
    """A newline splits the row across lines, breaking its shape exactly as a
    `|` does — same silent-disappearance risk."""
    import pytest
    with pytest.raises(ValueError, match="line break"):
        aide.set_gate_status(_progress(AWAITING), 1, "approved", "line one\nline two")


def test_a_stage_gate_naming_a_missing_stage_says_it_holds_nothing():
    """Otherwise a typo'd stage number reads as a guarded stage while blocking
    nothing at all — the failure the warning exists to surface."""
    rows = "| G | stage 99 | ⏳ Awaiting | — |"
    w = aide.gate_warnings(_lines(rows))[0]
    assert "holds NOTHING" in w and "check the stage number" in w


def test_a_stage_gate_with_real_items_reports_its_stage_plainly():
    assert "stage 1" in aide.gate_warnings(_lines(STAGE))[0]
    assert "holds NOTHING" not in aide.gate_warnings(_lines(STAGE))[0]


def _lines_with_planned_empty_stage(rows: str):
    """Lines of a document carrying a `📋` Stage 2 whose deliverables name no
    item — the state every stage is in before anything has been queued for it."""
    return (_progress(rows) + """
## Stage 2 — Later — 📋

**Deliverables.**
- 📋 C. Nothing queued for this yet.

**Acceptance.**
- [ ] Later works.
""").splitlines()


def test_a_gate_on_a_real_but_unqueued_stage_is_not_called_a_typo():
    """The primary documented use — raise the gate at planning time, before the
    stage has items. Reporting that as a mistyped stage number is the check
    firing on the feature's own happy path, which teaches the reader to ignore
    it."""
    rows = "| External data approved | stage 2 | ⏳ Awaiting | — |"
    w = aide.gate_warnings(_lines_with_planned_empty_stage(rows))[0]
    assert "holds NOTHING" not in w
    assert "check the stage number" not in w


def test_that_gate_still_says_it_holds_nothing_today():
    """Neutral, but not silent: the gate blocks no item right now and the
    reader should not read `stage 2` as work already held."""
    rows = "| External data approved | stage 2 | ⏳ Awaiting | — |"
    w = aide.gate_warnings(_lines_with_planned_empty_stage(rows))[0]
    assert "no items queued yet" in w
    assert "stage 2" in w


def test_a_missing_stage_is_still_reported_as_a_typo_alongside_a_real_one():
    """Both cases in one document: the check must not have been broadened into
    treating every empty reach as benign."""
    rows = ("| Real one | stage 2 | ⏳ Awaiting | — |\n"
            "| Typo one | stage 99 | ⏳ Awaiting | — |")
    w = aide.gate_warnings(_lines_with_planned_empty_stage(rows))
    assert "no items queued yet" in w[0] and "holds NOTHING" not in w[0]
    assert "holds NOTHING" in w[1] and "check the stage number" in w[1]


def test_zero_padding_does_not_turn_a_real_stage_into_a_typo():
    """`stage_section` matches numerically, so `stage 02` must find `Stage 2` —
    otherwise the padding alone decides whether the author is told they made a
    typo."""
    rows = "| External data approved | stage 02 | ⏳ Awaiting | — |"
    w = aide.gate_warnings(_lines_with_planned_empty_stage(rows))[0]
    assert "holds NOTHING" not in w
    assert "no items queued yet" in w


def test_stage_section_separates_absent_from_empty():
    """The distinction the warning rests on, asserted directly: both stages
    yield no item numbers, and only one of them exists."""
    lines = _lines_with_planned_empty_stage("| G | stage 2 | ⏳ Awaiting | — |")
    assert aide.stage_item_numbers(lines, "2") == []
    assert aide.stage_item_numbers(lines, "99") == []
    assert aide.stage_section(lines, "2") is not None
    assert aide.stage_section(lines, "99") is None


def test_a_malformed_row_with_an_empty_first_cell_still_warns():
    """`set("") <= set("-: ")` is true, so an empty first cell used to read as a
    separator row and the malformed-row warning never fired — the vanishing
    gate the warning exists to catch, hiding inside the warning itself."""
    rows = "| | 028 | ⏳ Awaiting | note with | a pipe |"
    assert any("being SKIPPED" in w for w in aide.gate_warnings(_lines(rows)))


def test_an_unnamed_but_well_formed_gate_still_blocks():
    """Failing safe: a row with no gate text is odd, but it must not silently
    stop blocking — that is the direction that loses work."""
    rows = "|  | 028 | ⏳ Awaiting | — |"
    blocked, _ = aide.gate_blocked_items(_lines(rows))
    assert blocked == {28}


def test_the_real_separator_row_is_still_ignored():
    assert aide.gate_warnings(_lines(AWAITING)) == aide.gate_warnings(_lines(AWAITING))
    assert len(aide.human_gates(_lines(AWAITING))) == 1


def test_resolving_a_gate_does_not_prepend_a_bom(tmp_path: Path):
    """Read tolerantly, write clean — `utf-8-sig` writes the BOM it strips."""
    repo = _repo(tmp_path, "| Pick a schema | Stage 1 | ⏳ Awaiting | |")
    ppath = repo / "docs" / "aide" / "progress.md"
    assert not ppath.read_bytes().startswith(b"\xef\xbb\xbf")
    assert aide.main(["--repo", str(repo), "gate", "approve", "1",
                      "--evidence", "chose X", "--no-commit"]) == 0
    assert not ppath.read_bytes().startswith(b"\xef\xbb\xbf")


def test_a_bom_already_in_the_file_is_stripped_not_preserved(tmp_path: Path):
    """The tolerant read is what removes it; the clean write keeps it removed."""
    repo = _repo(tmp_path, "| Pick a schema | Stage 1 | ⏳ Awaiting | |")
    ppath = repo / "docs" / "aide" / "progress.md"
    ppath.write_bytes(b"\xef\xbb\xbf" + ppath.read_bytes())
    assert aide.main(["--repo", str(repo), "gate", "approve", "1",
                      "--no-commit"]) == 0
    assert not ppath.read_bytes().startswith(b"\xef\xbb\xbf")
