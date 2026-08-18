"""Tests for the checks that hold documents and tests to conventions.md.

Each rule here was stated in the conventions and enforced by nothing. A stated
rule with no check decays — demonstrated twice in this framework's own history:
the slot-in-guidance rule was violated in two consecutive PRs, and the first
guard written for it had a blind spot that let it be violated again.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_shape", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]

TOML = '[project]\nname = "D"\ndocs_dir = "docs/aide"\ntests_dir = "tests"\n'


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "aide" / "items").mkdir(parents=True)
    (repo / "docs" / "aide" / "queue").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "aide.toml").write_text(TOML, encoding="utf-8")
    return repo


def _cfg(repo: Path):
    return aide.load_config(repo)


# --------------------------------------------------------------------------- #
# nested deliverable bullets
# --------------------------------------------------------------------------- #
def _stage(deliverables: str) -> list:
    return f"## Stage 1 — Rules — 🚧\n\n**Deliverables.**\n{deliverables}\n".splitlines()


def test_nested_status_bullet_is_reported():
    """The parser matches indented bullets, so a nested one is COUNTED as a full
    deliverable — it reads as subordinate to a human while the rollup treats it
    as a peer. (Not "ignored": that was the first wording, and it was backwards.
    A test asserting the observed statuses is further down this file.)"""
    w = aide.nested_deliverable_warnings(_stage("- ✅ A. *(Item 027)*\n  - 🚧 sub. *(Item 028)*"))
    assert len(w) == 1 and "nested status bullet" in w[0]


def test_flat_bullets_are_silent():
    assert aide.nested_deliverable_warnings(
        _stage("- ✅ A. *(Item 027)*\n- 📋 B. *(Item 028)*")) == []


def test_nested_bullet_without_an_icon_is_fine():
    """Only a nested bullet CARRYING status is ambiguous; plain prose is not."""
    assert aide.nested_deliverable_warnings(
        _stage("- ✅ A. *(Item 027)*\n  - a note with no icon")) == []


# --------------------------------------------------------------------------- #
# header blockquote
# --------------------------------------------------------------------------- #
def test_missing_blockquote_is_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    d = repo / "docs" / "aide"
    (d / "progress.md").write_text("# P\n\nStraight into prose.\n", encoding="utf-8")
    w = aide.header_blockquote_warnings(d)
    assert len(w) == 1 and "no header blockquote" in w[0]


def test_blockquote_present_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    d = repo / "docs" / "aide"
    (d / "progress.md").write_text("# P\n\n> **Status:** Draft\n", encoding="utf-8")
    assert aide.header_blockquote_warnings(d) == []


def test_an_html_comment_before_the_blockquote_is_allowed(tmp_path: Path):
    """Templates open with a comment the author deletes; it must not read as
    the missing blockquote."""
    repo = _repo(tmp_path)
    d = repo / "docs" / "aide"
    (d / "roadmap.md").write_text("<!-- note -->\n# R\n\n> **Status:** Draft\n",
                                  encoding="utf-8")
    assert aide.header_blockquote_warnings(d) == []


def test_generated_docs_are_not_checked(tmp_path: Path):
    """Only the templated living documents carry a blockquote. A generated
    artifact or a project note under docs_dir is not one — checking those was
    3 false positives out of 8 files when measured against a real consumer."""
    repo = _repo(tmp_path)
    d = repo / "docs" / "aide"
    (d / "feature_catalogue.generated.md").write_text("# Generated\n\ntable\n",
                                                      encoding="utf-8")
    (d / "insights.md").write_text("# Insight Inbox\n\n_Entries below._\n", encoding="utf-8")
    assert aide.header_blockquote_warnings(d) == []


# --------------------------------------------------------------------------- #
# item spec shape
# --------------------------------------------------------------------------- #
def _spec_file(repo: Path, name: str, text: str) -> None:
    (repo / "docs" / "aide" / "items" / name).write_text(text, encoding="utf-8")


GOOD_SPEC = "# Item 027 — Bounds\n\n> **Created:** 2026-08-18\n\n---\n\n## Assumptions\n\nNone.\n"


def test_a_good_spec_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md", GOOD_SPEC)
    assert aide.item_spec_warnings(repo / "docs" / "aide") == []


def test_heading_disagreeing_with_the_filename_is_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md", GOOD_SPEC.replace("Item 027", "Item 028"))
    w = aide.item_spec_warnings(repo / "docs" / "aide")
    assert any("matching the filename" in x for x in w)


def test_a_status_field_in_the_header_is_reported(tmp_path: Path):
    """Status lives only in progress.md; a duplicate has no owner and drifts."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md",
               GOOD_SPEC.replace("> **Created:**", "> **Status:** done\n> **Created:**"))
    w = aide.item_spec_warnings(repo / "docs" / "aide")
    assert any("'Status' field" in x for x in w)


def test_both_bold_field_spellings_are_caught(tmp_path: Path):
    """The template writes `**Created:**` with the colon INSIDE the bold, so a
    pattern expecting `**Status**:` matches nothing and the check silently
    never fires — caught only because a test asserted the real template shape."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-a.md", GOOD_SPEC.replace("> **Created:**", "> **Status:** x\n> **Created:**"))
    _spec_file(repo, "028-b.md", GOOD_SPEC.replace("Item 027", "Item 028").replace(
        "> **Created:**", "> **Completed**: y\n> **Created:**"))
    w = aide.item_spec_warnings(repo / "docs" / "aide")
    assert sum("field" in x for x in w) == 2


def test_a_status_word_after_the_header_is_not_flagged(tmp_path: Path):
    """Only the header carries the ban — body prose may discuss status freely."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md", GOOD_SPEC + "\n**Status**: discussed in prose.\n")
    assert aide.item_spec_warnings(repo / "docs" / "aide") == []


def test_missing_assumptions_is_aggregated_into_one_warning(tmp_path: Path):
    """32 of 112 specs predated the rule in the consumer measured against.
    Thirty-two separate warnings would bury the substantive ones — the failure
    mode issue #13 was filed for."""
    repo = _repo(tmp_path)
    for n in range(1, 13):
        _spec_file(repo, f"{n:03d}-x.md", f"# Item {n:03d} — X\n\n> **Created:** 2026-08-18\n")
    w = aide.item_spec_warnings(repo / "docs" / "aide")
    assumption_warnings = [x for x in w if "Assumptions" in x]
    assert len(assumption_warnings) == 1
    assert "12 item spec(s)" in assumption_warnings[0] and "+4 more" in assumption_warnings[0]


# --------------------------------------------------------------------------- #
# test hygiene lints
# --------------------------------------------------------------------------- #
def test_str_of_a_relative_path_is_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        "names = sorted(str(p.relative_to(root)) for p in tree)\n", encoding="utf-8")
    w = aide.separator_dependent_test_warnings(repo, _cfg(repo))
    assert len(w) == 1 and "as_posix" in w[0]


def test_fstring_interpolated_path_is_reported(tmp_path: Path):
    """An f-string calls str() too — this was the third recorded instance."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        'loc = f"{path.relative_to(ddir)}:{lineno}"\n', encoding="utf-8")
    assert len(aide.separator_dependent_test_warnings(repo, _cfg(repo))) == 1


def test_as_posix_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        "names = sorted(p.relative_to(root).as_posix() for p in tree)\n", encoding="utf-8")
    assert aide.separator_dependent_test_warnings(repo, _cfg(repo)) == []


def test_shelling_out_to_the_cli_is_reported(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        'import subprocess\nsubprocess.run(["python", ".aide/scripts/aide.py", "check"])\n',
        encoding="utf-8")
    w = aide.cli_subprocess_test_warnings(repo, _cfg(repo))
    assert len(w) == 1 and "call the function instead" in w[0]


def test_a_docstring_mentioning_the_cli_is_not_flagged(tmp_path: Path):
    """Measured against a real consumer, the ONLY textual match was a docstring
    explaining why the author had removed a subprocess. A line-based lint flags
    the file documenting the correct practice, so this one walks the AST."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        'def f():\n    """Calls run_checks rather than shelling out to aide.py\n'
        '    via subprocess.run, which failed on Windows."""\n    return 1\n',
        encoding="utf-8")
    assert aide.cli_subprocess_test_warnings(repo, _cfg(repo)) == []


def test_an_unparseable_test_file_does_not_crash_the_check(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text("def broken(:\n", encoding="utf-8")
    assert aide.cli_subprocess_test_warnings(repo, _cfg(repo)) == []


def test_one_warning_per_file(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        "a = str(p.relative_to(r))\nb = str(q.relative_to(r))\n", encoding="utf-8")
    assert len(aide.separator_dependent_test_warnings(repo, _cfg(repo))) == 1


def test_bold_emphasis_in_the_header_is_not_a_status_field(tmp_path: Path):
    """A field needs a colon beside the bold. Matching bare `**Status**`
    anywhere in the header flags prose that merely emphasises the word."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md",
               GOOD_SPEC.replace("> **Created:**",
                                 "> Tracks **Status** only in progress.md\n> **Created:**"))
    assert aide.item_spec_warnings(repo / "docs" / "aide") == []


def test_a_status_field_outside_the_blockquote_is_not_flagged(tmp_path: Path):
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md",
               "# Item 027 — Bounds\n\n**Status:** prose, not a header field\n\n"
               "> **Created:** 2026-08-18\n\n---\n\n## Assumptions\n\nNone.\n")
    assert aide.item_spec_warnings(repo / "docs" / "aide") == []


def test_blockquote_warning_path_is_relative_to_docs_dir(tmp_path: Path):
    """Consistent with `progress.md:12` and `items/…`, not `docs/aide/items/…`."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md", "# Item 027 — B\n\nno blockquote\n\n## Assumptions\n\nNone.\n")
    w = aide.header_blockquote_warnings(repo / "docs" / "aide")
    assert w and w[0].startswith("items/027-bounds.md:")


def test_nested_bullet_warning_states_the_real_behaviour():
    """The parser matches indented bullets, so a nested one is COUNTED, not
    ignored — verified: ['complete', 'planned'] rolls up to in-progress. The
    first wording claimed the opposite."""
    lines = _stage("- ✅ A. *(Item 027)*\n  - 📋 sub. *(Item 028)*")
    start, end, _ = aide.stage_sections(lines)[0]
    assert aide.stage_deliverable_statuses(lines, start, end) == ["complete", "planned"]
    assert aide.rollup_status(["complete", "planned"]) == "in-progress"
    assert "counts it as a full deliverable" in aide.nested_deliverable_warnings(lines)[0]


def test_a_dict_literal_holding_a_relative_path_is_not_flagged(tmp_path: Path):
    """`{p.relative_to(root): 1}` never stringifies the Path. A regex cannot
    tell it from an f-string's `{...}`, which is why this walks the AST — a lint
    that cries wolf stops being read."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        "counts = {p.relative_to(root): 1}\nseen = {p.relative_to(root)}\n",
        encoding="utf-8")
    assert aide.separator_dependent_test_warnings(repo, _cfg(repo)) == []


def test_tests_dir_outside_the_repo_does_not_crash_either_lint(tmp_path: Path):
    """The same ValueError fixed once in absolute_path_test_warnings came back
    in two new lints written beside it. All three now share one helper."""
    repo = _repo(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "test_x.py").write_text(
        'import subprocess\nsubprocess.run(["python", "aide.py", "check"])\n'
        "n = str(p.relative_to(root))\n", encoding="utf-8")
    (repo / "aide.toml").write_text(
        f'[project]\nname = "D"\ndocs_dir = "docs/aide"\ntests_dir = "{outside.as_posix()}"\n',
        encoding="utf-8")
    cfg = aide.load_config(repo)
    assert len(aide.separator_dependent_test_warnings(repo, cfg)) == 1   # must not raise
    assert len(aide.cli_subprocess_test_warnings(repo, cfg)) == 1
    assert len(aide.absolute_path_test_warnings(repo, cfg)) == 0


def test_str_and_fstring_are_both_still_caught(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text("x = str(p.relative_to(r))\n", encoding="utf-8")
    (repo / "tests" / "test_b.py").write_text('y = f"{p.relative_to(r)}:1"\n', encoding="utf-8")
    assert len(aide.separator_dependent_test_warnings(repo, _cfg(repo))) == 2


def test_str_around_an_already_normalised_path_is_silent(tmp_path: Path):
    """`str(p.relative_to(root).as_posix())` is separator-stable — it is the
    rule being followed. Searching the subtree for `.relative_to(` flagged it;
    only the OUTERMOST call may decide."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        "a = str(p.relative_to(root).as_posix())\n", encoding="utf-8")
    assert aide.separator_dependent_test_warnings(repo, _cfg(repo)) == []


def test_fstring_around_an_already_normalised_path_is_silent(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "tests" / "test_x.py").write_text(
        'a = f"{p.relative_to(root).as_posix()}:{n}"\n', encoding="utf-8")
    assert aide.separator_dependent_test_warnings(repo, _cfg(repo)) == []


def test_the_bare_shape_is_still_caught_after_narrowing(tmp_path: Path):
    """The narrowing must not silence the recorded defect itself."""
    repo = _repo(tmp_path)
    (repo / "tests" / "test_a.py").write_text("a = str(p.relative_to(root))\n", encoding="utf-8")
    (repo / "tests" / "test_b.py").write_text('b = f"{p.relative_to(d)}:{n}"\n', encoding="utf-8")
    assert len(aide.separator_dependent_test_warnings(repo, _cfg(repo))) == 2


def test_a_nested_bullet_outside_deliverables_is_still_reported():
    """Scoping to the Deliverables block would UNDER-report: the rollup reads
    every leading-icon bullet in the section, so an indented one under
    Acceptance drags the stage exactly the same way. Verified here rather than
    assumed."""
    lines = ("## Stage 1 — S — ✅\n\n**Deliverables.**\n- ✅ Done. *(Item 027)*\n\n"
             "**Acceptance.**\n- [x] Ticked.\n  - 📋 nested, outside Deliverables\n").splitlines()
    start, end, _ = aide.stage_sections(lines)[0]
    assert aide.stage_deliverable_statuses(lines, start, end) == ["complete", "planned"]
    assert aide.rollup_status(["complete", "planned"]) == "in-progress"
    assert len(aide.nested_deliverable_warnings(lines)) == 1


def test_a_heading_after_the_title_does_not_satisfy_the_blockquote(tmp_path: Path):
    """"Opens with a blockquote" means the NEXT thing. Skipping further headers
    let `# Title` / `## Intro` / `> …` pass."""
    repo = _repo(tmp_path)
    (repo / "docs" / "aide" / "progress.md").write_text(
        "# P\n\n## Intro\n\n> **Status:** Draft\n", encoding="utf-8")
    assert len(aide.header_blockquote_warnings(repo / "docs" / "aide")) == 1


def test_a_multi_line_html_comment_is_skipped_whole(tmp_path: Path):
    """Only the opening line starts with `<!--`, so a line-by-line test lets the
    comment body read as content and reports a false positive."""
    repo = _repo(tmp_path)
    (repo / "docs" / "aide" / "roadmap.md").write_text(
        "<!--\n  Template guidance spanning\n  several lines.\n-->\n"
        "# R\n\n> **Status:** Draft\n", encoding="utf-8")
    assert aide.header_blockquote_warnings(repo / "docs" / "aide") == []


def test_a_heading_without_a_title_is_reported(tmp_path: Path):
    """`# Item 027` alone gives the status report no title to parse, so the
    check must require the documented `— Title` too, not just the number."""
    repo = _repo(tmp_path)
    _spec_file(repo, "027-bounds.md", GOOD_SPEC.replace("# Item 027 — Bounds", "# Item 027"))
    w = aide.item_spec_warnings(repo / "docs" / "aide")
    assert any("matching the filename" in x for x in w)


def test_all_three_dash_styles_are_accepted(tmp_path: Path):
    repo = _repo(tmp_path)
    for n, dash in ((27, "—"), (28, "–"), (29, "-")):
        _spec_file(repo, f"{n:03d}-x.md",
                   GOOD_SPEC.replace("# Item 027 — Bounds", f"# Item {n:03d} {dash} X"))
    assert aide.item_spec_warnings(repo / "docs" / "aide") == []
