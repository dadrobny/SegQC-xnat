"""Tests for amending an acceptance attestation — conventions.md §1 → progress.md.

The recorded defect (issue #118, spine-failure-lab under engine 1.22.0): a
Stage 0 box was ticked with the evidence "run on this CPU-only machine" on a
workstation with four GPUs. ``accept`` reports an already-ticked box as
"unchanged", so there was no CLI path to the correction at all, and it landed
as a hand edit of ``progress.md`` in a PR review — the one edit every role is
otherwise forbidden from making.

The guard against over-use is structural rather than advisory, and these tests
are what pin it: ``amend`` can only **add**, so it cannot be used to make an
inconvenient attestation agree with a shipped stage, and ``reword`` — the one
verb that edits in place — refuses the moment anything has been claimed
against the wording it would change.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_acceptance_amend", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


PROGRESS = """\
# P

## Stage 1 — Foundations — 🚧

**Deliverables.**
- 📋 The greeter. *(Item 001)*

**Acceptance.**
- [x] The benchmark runs end to end. *(validator, 2026-08-29: on this CPU-only machine)*
- [ ] The CLI reports a non-zero exit on failure.
"""

ROADMAP = """\
# R

## Stage 1 — Foundations

**Validation / acceptance.**

- The benchmark runs end to end.
- The CLI reports a non-zero exit on failure.
- Target: throughput above 100 rps.
"""


# --------------------------------------------------------------------------- #
# amend — append-only, and that is the guard
# --------------------------------------------------------------------------- #
def test_amend_appends_a_dated_trail_line_below_the_box():
    out, msg = aide.amend_criterion(
        PROGRESS, "1", 1, "the host has four GPUs; the run used CUDA", "2026-09-01")
    lines = out.splitlines()
    box = lines.index(
        "- [x] The benchmark runs end to end. "
        "*(validator, 2026-08-29: on this CPU-only machine)*")
    assert lines[box + 1] == (
        "  - **2026-09-01** → the host has four GPUs; the run used CUDA")
    assert "amended" in msg


def test_amend_never_touches_the_original_attestation():
    """The whole guard against over-use: the verb can only add."""
    original = [l for l in PROGRESS.splitlines() if l.startswith("- [x]")]
    out, _ = aide.amend_criterion(PROGRESS, "1", 1, "a correction", "2026-09-01")
    assert [l for l in out.splitlines() if l.startswith("- [x]")] == original


def test_a_second_amend_lands_below_the_first_newest_last():
    out, _ = aide.amend_criterion(PROGRESS, "1", 1, "first", "2026-09-01")
    out, _ = aide.amend_criterion(out, "1", 1, "second", "2026-09-02")
    trail = [l for l in out.splitlines() if l.lstrip().startswith("- **")]
    assert trail == ["  - **2026-09-01** → first", "  - **2026-09-02** → second"]


def test_amend_follows_an_existing_trails_indentation():
    seeded = PROGRESS.replace(
        "- [ ] The CLI", "    - **2026-08-30** → hand-written trail\n- [ ] The CLI")
    out, _ = aide.amend_criterion(seeded, "1", 1, "next", "2026-09-01")
    assert "    - **2026-09-01** → next" in out.splitlines()


def test_amend_refuses_an_unticked_box():
    with pytest.raises(ValueError, match="no attestation to amend"):
        aide.amend_criterion(PROGRESS, "1", 2, "x", "2026-09-01")


def test_amend_refuses_an_unknown_stage_and_an_out_of_range_criterion():
    with pytest.raises(ValueError, match="no Stage 9"):
        aide.amend_criterion(PROGRESS, "9", 1, "x", "2026-09-01")
    with pytest.raises(ValueError, match="out of range"):
        aide.amend_criterion(PROGRESS, "1", 7, "x", "2026-09-01")


# --------------------------------------------------------------------------- #
# retract — unticks, keeps the original visible, stays findable afterwards
# --------------------------------------------------------------------------- #
def test_retract_unticks_the_box_and_keeps_the_original_annotation():
    out, msg = aide.retract_criterion(PROGRESS, "1", 1, "the host was misread",
                                      "2026-09-02")
    lines = out.splitlines()
    assert lines[8] == (
        "- [ ] The benchmark runs end to end. "
        "*(validator, 2026-08-29: on this CPU-only machine)*")
    assert lines[9] == "  - **2026-09-02** → retracted: the host was misread"
    assert "retracted" in msg


def test_retract_refuses_a_box_that_was_never_ticked():
    with pytest.raises(ValueError, match="already unticked"):
        aide.retract_criterion(PROGRESS, "1", 2, "x", "2026-09-02")


def test_a_retraction_is_readable_back_out_of_the_trail():
    """`check` and `status` surface it, so it must survive as data, not prose."""
    out, _ = aide.retract_criterion(PROGRESS, "1", 1, "the host was misread",
                                    "2026-09-02")
    assert aide.retracted_criteria(out.splitlines()) == [
        ("1", 1, "2026-09-02", "the host was misread")]


def test_a_plain_amendment_is_not_read_as_a_retraction():
    out, _ = aide.amend_criterion(PROGRESS, "1", 1, "just a correction", "2026-09-01")
    assert aide.retracted_criteria(out.splitlines()) == []


def test_a_trail_line_is_not_counted_as_a_deliverable_or_a_box():
    """A trail must not disturb the rollup or shift a criterion's index."""
    out, _ = aide.amend_criterion(PROGRESS, "1", 1, "a correction", "2026-09-01")
    lines = out.splitlines()
    start, end, _ = aide.stage_section(lines, "1")
    assert aide.stage_deliverable_statuses(lines, start, end) == ["planned"]
    assert len(aide.acceptance_boxes(lines, start, end)) == 2
    assert aide.nested_deliverable_warnings(lines) == []


# --------------------------------------------------------------------------- #
# reword — the one in-place edit, and its mechanical precondition
# --------------------------------------------------------------------------- #
def test_reword_rewrites_an_untouched_criterion():
    out, old = aide.reword_criterion(PROGRESS, "1", 2, "The CLI exits non-zero on any failure.")
    assert old == "The CLI reports a non-zero exit on failure."
    assert "- [ ] The CLI exits non-zero on any failure." in out.splitlines()


def test_reword_refuses_a_ticked_criterion():
    with pytest.raises(ValueError, match="is ticked"):
        aide.reword_criterion(PROGRESS, "1", 1, "something else")


def test_reword_refuses_an_annotated_criterion_even_once_unticked():
    """A retraction leaves the box open but the wording still spoken for."""
    out, _ = aide.retract_criterion(PROGRESS, "1", 1, "misread", "2026-09-02")
    with pytest.raises(ValueError, match="carries an annotation"):
        aide.reword_criterion(out, "1", 1, "something else")


def test_reword_refuses_a_criterion_carrying_a_correction_trail():
    seeded = PROGRESS.replace(
        "- [ ] The CLI reports a non-zero exit on failure.",
        "- [ ] The CLI reports a non-zero exit on failure.\n"
        "  - **2026-08-30** → someone already said something about this")
    with pytest.raises(ValueError, match="carries a correction trail"):
        aide.reword_criterion(seeded, "1", 2, "something else")


def test_reword_refuses_text_carrying_a_line_break():
    with pytest.raises(ValueError, match="line break"):
        aide.reword_criterion(PROGRESS, "1", 2, "one\ntwo")


# --------------------------------------------------------------------------- #
# the roadmap mirror — both documents or neither
# --------------------------------------------------------------------------- #
def test_roadmap_acceptance_bullets_skip_a_target_bullet():
    """A measured outcome is not a box, so it must not consume an index."""
    lines = ROADMAP.splitlines()
    assert [lines[i] for i in aide.roadmap_acceptance_bullets(lines, "1")] == [
        "- The benchmark runs end to end.",
        "- The CLI reports a non-zero exit on failure.",
    ]


def test_roadmap_acceptance_bullets_are_none_when_the_stage_has_no_block():
    assert aide.roadmap_acceptance_bullets(
        "# R\n\n## Stage 1 — Foundations\n\nProse only.\n".splitlines(), "1") is None


def test_reword_mirrors_into_the_matching_roadmap_bullet():
    out, err = aide.reword_roadmap_bullet(ROADMAP, "1", 2, "The CLI exits non-zero.", 2)
    assert err is None
    assert "- The CLI exits non-zero." in out.splitlines()
    assert "- Target: throughput above 100 rps." in out.splitlines()


def test_a_roadmap_that_cannot_be_lined_up_writes_nothing_and_says_why():
    out, err = aide.reword_roadmap_bullet(ROADMAP, "1", 2, "x", 5)
    assert out is None
    assert "2 acceptance bullets" in err and "5 boxes" in err


def test_a_stage_with_no_acceptance_block_is_not_an_error():
    """No mirror is a different situation from a mirror that disagrees."""
    out, err = aide.reword_roadmap_bullet(
        "# R\n\n## Stage 1 — Foundations\n\nProse only.\n", "1", 1, "x", 2)
    assert out is None and err is None
