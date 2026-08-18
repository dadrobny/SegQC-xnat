"""Tests for item 114 -- documentation corrections: ``bounds.py`` comments
naming retired labels, and Stage 17's self-contradicting acceptance box.

Covers AC1-AC8. AC9 (whether ``aide check``'s rollup mechanically requires
every acceptance box ticked before a stage may be ``✅``) is left to the
builder's empirical evidence recorded in the item spec/Decisions log --
deliberately not pinned here, since the answer is not yet known at test-write
time and a test pinning the wrong answer would be worse than no test.

AC9's answer is now settled upstream rather than inferred: engine 1.5.0 took
acceptance boxes out of the derivation entirely -- the rollup skips checkbox
lines, no ``aide check`` rule gates a ``✅`` stage on them, and
``aide progress set`` leaves them as the author wrote them
(``.aide/conventions.md`` §1). A stage may be ``✅`` with an unticked box, and
ticking is the explicit ``aide progress accept``. So AC4 below is a plain
durable assertion; until 1.5.0 landed here it doubled as a deliberate tripwire
for the force-tick defect, since any ``progress set`` call for any item would
re-tick the box (``insights.md``, item 114/115 entries → aide-loop PR #32).

Two unrelated fixes, batched (see item spec):

(a) ``src/segfacet/heuristics/bounds.py`` comments still name labels retired
    by item 093 (``S``, ``Cocygis``) when the TPTBox convention became
    default. Behaviour (derived generically from ``CANONICAL_ORDER`` by name
    prefix) must not change -- AC3 pins that behaviour directly rather than
    relying on a comment-only diff.
(b) ``docs/aide/progress.md``'s Stage 17 fourth acceptance box reads
    ``- [x]`` while its own annotation opens by explaining it was *not*
    ticked. The box gets unticked; the annotation stays, reworded to explain
    rather than contradict; Stage 17 stays ``✅``.

Until the builder lands the fix, AC1/AC3(partially)/AC4/AC5 are *expected to
fail* -- that is the correct pre-implementation state.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from segfacet.heuristics.bounds import _level_group
from segfacet.labels import CANONICAL_ORDER

REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDS_PY_PATH = REPO_ROOT / "src" / "segfacet" / "heuristics" / "bounds.py"
PROGRESS_MD_PATH = REPO_ROOT / "docs" / "aide" / "progress.md"
AIDE_SCRIPT = REPO_ROOT / ".aide" / "scripts" / "aide.py"

# =========================================================================== #
# AC1: no retired label name survives in bounds.py
# =========================================================================== #
#
# Matching rule (documented here so a future reader knows what is and is not
# caught): we flag (1) the literal word ``Cocygis`` anywhere, exact word
# boundary, plus (2) a bare ``S`` used as a *label name* -- which in this
# file only ever appears immediately adjacent to ``Cocygis`` in a
# label-list context: RST inline-code (` ``S`` `), a parenthesised list
# (``(S,``), a ``#``-comment list (``# S,``), or prose (``S and Cocygis``).
# We deliberately do NOT flag every bare occurrence of the character/word
# "S" -- that would false-positive on ordinary prose and identifiers
# (e.g. "AC13", "This", "severity"). Because every current bare-S-as-label
# site in this file sits directly beside "Cocygis", anchoring the S-pattern
# on that adjacency is sufficient and avoids the false-positive trap the
# item's adversarial note warns about.
#
# Adversarial: a retired name inside a docstring example must still be
# caught -- we do not special-case docstrings vs. comments; the pattern is
# applied to the raw file text (docstrings included), so an example embedded
# in a docstring is caught, not exempted.
RETIRED_NAME_PATTERN = re.compile(
    r"\bCocygis\b"          # retired label name, exact word
    r"|``S``"                # bare S in RST inline-code list context
    r"|\(S,\s*Cocygis"       # "(S, Cocygis" parenthesised list context
    r"|#\s*S,\s*Cocygis"     # "# S, Cocygis" inline-comment list context
    r"|\bS\s+and\s+Cocygis\b"  # "S and Cocygis" prose context
)


def _bounds_py_text() -> str:
    return BOUNDS_PY_PATH.read_text(encoding="utf-8")


def test_ac1_no_retired_label_name_in_bounds_py_source():
    text = _bounds_py_text()
    matches = [
        (i + 1, line)
        for i, line in enumerate(text.splitlines())
        if RETIRED_NAME_PATTERN.search(line)
    ]
    assert not matches, (
        "bounds.py still names a retired label (S / Cocygis) at these "
        f"lines: {matches}"
    )


def test_ac1_pattern_catches_retired_name_inside_a_docstring_example():
    # Adversarial: a retired name embedded in a docstring example must still
    # be caught, not silently exempted just because it's inside triple
    # quotes.
    docstring_snippet = (
        '    """Example.\n'
        "\n"
        "    e.g. S and Cocygis are unbounded.\n"
        '    """\n'
    )
    assert RETIRED_NAME_PATTERN.search(docstring_snippet), (
        "the retired-name pattern must catch an example embedded in a "
        "docstring, not just top-level comments"
    )


def test_ac1_pattern_does_not_false_positive_on_ordinary_prose():
    # Guards the "not on every occurrence of the character S" promise.
    ordinary = (
        "This severity is AC13's stable order. Missing keys are skipped. "
        "S1-S6 and Cocc are unbounded; This function returns None."
    )
    assert not RETIRED_NAME_PATTERN.search(ordinary), (
        "the retired-name pattern must not fire on ordinary prose/identifiers "
        "that merely contain the letter S"
    )


# =========================================================================== #
# AC2: the replacement text names the labels actually omitted today
# =========================================================================== #


def test_ac2_current_sacral_and_coccygeal_names_are_named():
    text = _bounds_py_text()
    assert re.search(r"\bS1\b", text), "bounds.py should name S1 (currently omitted)"
    assert re.search(r"\bS6\b", text), "bounds.py should name S6 (currently omitted)"
    assert re.search(r"\bCocc\b", text), "bounds.py should name Cocc (currently omitted)"


def test_ac2_describes_generic_derivation_not_a_hardcoded_list():
    text = _bounds_py_text().lower()
    assert "prefix" in text, (
        "bounds.py's comments should describe the generic name-prefix "
        "derivation (AC2), not just list the omitted names"
    )


# =========================================================================== #
# AC3: behaviour is byte-identical -- direct behavioural pin on _level_group
# =========================================================================== #
#
# A comment-only diff cannot be caught by a comment-text assertion, and the
# existing golden/corpus tests already cover the end-to-end path. This pins
# the one thing that *could* silently regress if someone "simplified" the
# derivation while rewriting the comments: dropping the isdigit() guard,
# which would misclassify "Cocc" as cervical (it starts with "C") and start
# emitting spurious bounds findings for it.


def test_ac3_sacral_and_coccygeal_names_are_unbounded():
    # S1-S6 and Cocc must resolve to no bounds group (None) -- derived from
    # CANONICAL_ORDER itself, not hardcoded as a literal name list.
    for name in CANONICAL_ORDER:
        if name == "Cocc" or (name.startswith("S") and name[1:].isdigit()):
            assert _level_group(name) is None, (
                f"{name!r} must remain unbounded (None) -- a comment-only "
                "edit must not change bounds behaviour"
            )


def test_ac3_coccygeal_specifically_is_the_fragile_case():
    # "Cocc" starts with "C" -- the same letter as the cervical group -- so
    # it is the one name whose correct (None) classification depends
    # entirely on the isdigit() guard on the second character. This is the
    # single most fragile line in the file for a "just rewrite the comment"
    # change to silently break.
    assert _level_group("Cocc") is None


def test_ac3_cervical_thoracic_lumbar_names_are_bounded():
    for name in CANONICAL_ORDER:
        if name.startswith("C") and len(name) > 1 and name[1].isdigit():
            expected_prefix = "cervical"
        elif name.startswith("T") and name[1:].isdigit():
            expected_prefix = "thoracic"
        elif name.startswith("L") and name[1:].isdigit():
            expected_prefix = "lumbar"
        else:
            continue
        group = _level_group(name)
        assert group == expected_prefix, (
            f"{name!r} should resolve to group {expected_prefix!r}, got "
            f"{group!r}"
        )


def test_ac3_unknown_and_custom_names_remain_unbounded():
    assert _level_group("unknown") is None
    assert _level_group("some-custom-level") is None


# =========================================================================== #
# Stage 17 acceptance-box parsing helpers (AC4-AC7)
# =========================================================================== #


def _progress_md_text() -> str:
    return PROGRESS_MD_PATH.read_text(encoding="utf-8")


def _stage17_section(text: str) -> str:
    """Return Stage 17's full section text (heading through the line before
    the next '## Stage ' heading). Raises AssertionError -- loudly, never a
    silent pass -- if the section cannot be found (adversarial requirement).
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## Stage 17"):
            start = i
            break
    assert start is not None, (
        "Stage 17 section heading ('## Stage 17') not found in progress.md"
    )
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## Stage "):
            end = j
            break
    return "\n".join(lines[start:end])


def _fourth_acceptance_block(section: str) -> str:
    """Return the acceptance-bullet block (box line + its annotation
    paragraph, up to the next bullet/separator) whose text mentions the
    real-segmenter round-trip. Raises AssertionError if not found.
    """
    lines = section.splitlines()
    box_idx = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("- [") and "real segmenter output round-trips" in line:
            box_idx = i
            break
    assert box_idx is not None, (
        "Stage 17's 'real segmenter output round-trips' acceptance box not "
        "found in progress.md"
    )
    end = len(lines)
    for j in range(box_idx + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("---") or stripped.startswith("- [") or stripped == "":
            end = j
            break
    return "\n".join(lines[box_idx:end])


@pytest.fixture(scope="module")
def progress_text() -> str:
    return _progress_md_text()


@pytest.fixture(scope="module")
def stage17_section(progress_text) -> str:
    return _stage17_section(progress_text)


@pytest.fixture(scope="module")
def fourth_acceptance_block(stage17_section) -> str:
    return _fourth_acceptance_block(stage17_section)


# =========================================================================== #
# AC4: the box is unticked
# =========================================================================== #


def test_ac4_fourth_acceptance_box_is_unticked(fourth_acceptance_block):
    box_line = fourth_acceptance_block.splitlines()[0].lstrip()
    assert box_line.startswith("- [ ]"), (
        "Stage 17's fourth acceptance box (real segmenter output "
        f"round-trips) must read '- [ ]'; got: {box_line!r}"
    )
    assert not box_line.startswith("- [x]")


# =========================================================================== #
# AC5: the annotation is kept and reconciled
# =========================================================================== #


def test_ac5_annotation_still_present_and_explains_the_spineps_situation(
    fourth_acceptance_block,
):
    block = fourth_acceptance_block
    # The annotation (the parenthetical explanation) must still be present.
    assert "(" in block and ")" in block, (
        "the annotation (parenthetical explanation) must still be present"
    )
    lowered = block.lower()
    assert "spineps" in lowered, (
        "the annotation must still explain the SPINEPS-fixture situation"
    )
    assert "environment-gated" in lowered, (
        "the annotation must still cross-reference the Environment-Gated "
        "Capability Verification section"
    )


def test_ac5_annotation_no_longer_opens_by_contradicting_the_box(
    fourth_acceptance_block,
):
    # Before the fix, the annotation opens with "(Not ticked: ..." -- a
    # correction appropriate only for a *ticked* box. Now that the box
    # itself reads "- [ ]", an opening of that shape would be redundant at
    # best and actively confusing (explaining why something isn't ticked
    # right next to the box that already isn't ticked, phrased as if
    # correcting a reader's assumption that it was). We assert the specific
    # literal phrase is gone rather than banning "Not ticked" outright,
    # since a reworded annotation may still legitimately mention ticking.
    # Normalise whitespace (the annotation wraps across multiple lines in the
    # committed Markdown, so a contiguous substring check must not be fooled
    # by a line break landing between "(Not" and "ticked:").
    normalized = " ".join(fourth_acceptance_block.split())
    assert "(Not ticked:" not in normalized, (
        "the annotation must no longer open with '(Not ticked:' -- that "
        "phrasing corrects a ticked box, but the box is now unticked"
    )


# =========================================================================== #
# AC6: it agrees with the Environment-Gated verification row
# =========================================================================== #


def test_ac6_environment_gated_row_still_reads_unverified(progress_text):
    match = re.search(
        r"\|\s*Real SPINEPS-output label-convention round-trip\s*\|.*\|",
        progress_text,
    )
    assert match is not None, (
        "the 'Real SPINEPS-output label-convention round-trip' row must "
        "still exist in the Environment-Gated Capability Verification table"
    )
    # Find the full row (may wrap across the match; re-extract by line).
    row_line = next(
        line
        for line in progress_text.splitlines()
        if "Real SPINEPS-output label-convention round-trip" in line
    )
    assert "❓ Unverified" in row_line, (
        "the Environment-Gated row must still read '❓ Unverified'; got: "
        f"{row_line!r}"
    )


# =========================================================================== #
# AC7: Stage 17 stays ✅ (summary row and section heading unchanged)
# =========================================================================== #


def test_ac7_stage17_section_heading_still_carries_checkmark(stage17_section):
    heading = stage17_section.splitlines()[0]
    assert heading.startswith("## Stage 17")
    assert "✅" in heading, (
        f"Stage 17's section heading must still carry ✅; got: {heading!r}"
    )


def test_ac7_stage17_summary_row_still_carries_checkmark(progress_text):
    row = next(
        (
            line
            for line in progress_text.splitlines()
            if line.startswith("| 17 ")
        ),
        None,
    )
    assert row is not None, "Stage summary table must still have a Stage 17 row"
    assert "✅" in row, f"Stage 17's summary row must still show ✅; got: {row!r}"


# =========================================================================== #
# Adversarial: Stage 17 section / box not found must fail loudly
# =========================================================================== #


def test_adv_missing_stage17_heading_raises_assertion():
    text_without_stage17 = "# doc\n\n## Stage 16 — X — ✅\n\n## Stage 18 — Y — ✅\n"
    with pytest.raises(AssertionError):
        _stage17_section(text_without_stage17)


def test_adv_missing_acceptance_box_raises_assertion():
    section_without_box = "## Stage 17 — X — ✅\n\nNo acceptance boxes here.\n"
    with pytest.raises(AssertionError):
        _fourth_acceptance_block(section_without_box)


# =========================================================================== #
# AC8: no new `aide check` warning
# =========================================================================== #
#
# Pinned baseline (captured on this branch before item 114's changes landed,
# one commit after f9cb63f which fixed an unrelated item-113 insights.md
# entry that `aide check` hard-errors on): 7 location-stable warnings
# (progress.md/queue/insights.md format warnings unrelated to this item).
# Branch-state-dependent warnings are excluded entirely -- see
# `_BRANCH_STATE_WARNING_PREFIXES` below -- rather than risk a flaky CI
# failure for reasons unrelated to this item.
#
# Locations are pinned in POSIX form and compared as-is: engine 1.5.0 renders
# them with `.as_posix()`, so the same document reports identically on every
# platform. Before that fix they were built by f-stringing a `Path`, whose
# `str()` is OS-native, and `queue/queue-002.md:80` -- the one baseline entry
# with a subdirectory component -- was the single warning that broke the
# Windows CI leg while the six `docs/aide/`-root ones passed. This module
# carried a `_posix_location()` normaliser for that, retired once the engine
# fix landed here (insights.md, 2026-08-15 → aide-loop PR #32).
#
# Re-pin audit, engine 1.5.0 → 1.14.0 (2026-08-18): the upgrade raised five new
# location-based warnings from the five conventions rules 1.14.0 began
# enforcing. None was pinned -- every one was a real finding and was fixed in
# the same commit, so the baseline set below is unchanged: a `str(Path)` in
# `test_082_verse_build_recipe.py` (§6, OS separator), and a missing header
# blockquote plus a `# Item NNN: Title` heading in items 014 and 015, the two
# specs predating the template (the colon form makes the status report's title
# parse return nothing). The sixth new warning names no location; see
# `_AGGREGATED_WARNING_RES`.
_PINNED_BASELINE_WARNING_LOCATIONS = frozenset(
    {
        "progress.md:340",
        "progress.md:459",
        "progress.md:638",
        "queue/queue-002.md:80",
        "insights.md:51",
        "insights.md:58",
        "insights.md:60",
    }
)

_LOCATION_WARNING_RE = re.compile(r"^([^:]+:\d+):")

# Whole-corpus warnings that name no single location, so they cannot be pinned
# by one. Engine 1.14.0 added the first of them: the mandatory `## Assumptions`
# block, reported as ONE aggregated line because 32 of this repo's specs
# predate the convention and 32 separate warnings would bury the substantive
# ones. Back-filling them is explicitly not required (aide-loop CHANGELOG
# 1.6.0, "expected but not required"), so this is a standing, healthy state --
# and the count is matched loosely because it falls as new specs are written
# to the current template.
_AGGREGATED_WARNING_RES = (
    re.compile(r"^\d+ item spec\(s\) have no mandatory '## Assumptions' block:"),
)

# Warnings that depend on which branches happen to exist in the local
# checkout, in both shapes `run_checks` emits them (`.aide/scripts/aide.py`,
# the claim-branch agreement loop): a leftover claim branch for a finished
# item, and a prefixed branch matching neither the item nor the queue naming
# shape. Neither is location-based, and neither says anything about this
# item's documents -- a fresh checkout or a CI runner has different branches
# than any developer's working clone, so pinning them would be flaky for
# reasons unrelated to item 114.
_BRANCH_STATE_WARNING_PREFIXES = ("stale claim branch", "unrecognised branch")


def _aide_check_warnings() -> list:
    """Return `aide check`'s warnings as a list of strings.

    Calls ``run_checks`` in-process rather than shelling out to
    ``aide.py check`` and parsing stdout. The subprocess form failed on the
    Windows CI runner with ``proc.stdout is None`` despite
    ``capture_output=True`` -- a platform-specific capture failure that
    could not be reproduced on Linux, and one that would have been *worse*
    than a crash had it returned an empty string instead: the caller's loop
    iterates over the parsed lines, so an empty capture makes this test pass
    vacuously while checking nothing. ``run_checks`` is the same function
    ``cmd_check`` calls (``.aide/scripts/aide.py:1086``); it returns
    ``(errors, warnings)`` as structured data, so there is no stdout, no
    encoding and no subprocess to go wrong, and nothing to re-parse.
    """
    spec = importlib.util.spec_from_file_location("_aide_cli", AIDE_SCRIPT)
    aide = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aide)
    repo_root = aide.find_repo_root(REPO_ROOT)
    _errors, warnings = aide.run_checks(repo_root, aide.load_config(repo_root))
    return list(warnings)


def test_ac8_no_new_aide_check_warning_beyond_pinned_baseline():
    warnings = _aide_check_warnings()
    # A capture/plumbing failure must fail loudly, not silently skip the
    # loop below: `aide check` always reports the seven location-stable
    # baseline warnings on this branch.
    assert warnings, "run_checks returned no warnings at all -- expected the pinned baseline"
    for warning in warnings:
        if warning.startswith(_BRANCH_STATE_WARNING_PREFIXES):
            # Branch-state-dependent -- excluded, see the note above.
            continue
        if any(pattern.match(warning) for pattern in _AGGREGATED_WARNING_RES):
            # Whole-corpus, location-free -- excluded, see the note above.
            continue
        match = _LOCATION_WARNING_RE.match(warning)
        assert match is not None, (
            f"unrecognised aide check warning shape (not location-based, "
            f"not a branch-state warning): {warning!r}"
        )
        assert match.group(1) in _PINNED_BASELINE_WARNING_LOCATIONS, (
            f"aide check produced a new warning not in the pre-item-114 "
            f"baseline: {warning!r}"
        )
