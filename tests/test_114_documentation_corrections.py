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
from collections import Counter
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
#
# **The baseline is keyed by (path, text), not by location** -- changed
# 2026-08-25 after the line numbers moved three times without a single warning
# changing meaning:
#
#   1. engine 1.13.0's `## Human gates` table pushed `progress.md`'s three down
#      by 24;
#   2. engine 1.20.0's `| 🔍 | In Review |` legend row pushed them down by one
#      more;
#   3. `aide insights archive --before 2026-08-01` moved 42 closed entries out
#      of `insights.md`, taking its three from 51/58/60 to 31/32/33.
#
# Every one came from a framework verb legitimately rewriting a document it
# owns, and every one presented as a red test that reads like a regression. The
# churn was the visible cost; the real one was that a re-pin is a mechanical
# edit made while reading a failure, and nothing checked that each moved
# warning was the one the author believed it to be -- so a genuinely new
# warning arriving in the same run as a shift would have been folded into the
# baseline unnoticed. AC8's claim ("no new `aide check` warning") is about a
# warning's *identity*, and a line number is the one part of it the loop
# perturbs. Dropping the line number from the key makes the assertion immune to
# all three shifts while still failing on a real new finding.
#
# Kept deliberately: **the file path, and the count**. Text alone would collapse
# the three identical `insights.md` shape warnings into one key, so a fourth
# malformed entry would pass unnoticed -- the exact silent-green failure this
# module exists to prevent. Path alone would let a *different* warning about the
# same file through. The comparison is therefore a multiset: a key may appear no
# more often than its baseline count, and an unknown key fails.
#
# Fewer warnings never fails. The baseline records what is tolerated, not what
# is required, so fixing one of these documents does not turn this test red for
# doing the right thing -- and the three `insights.md` entries in particular
# cannot be fixed in this repo at all (their provenance names a queue or an
# item range, which `_INSIGHT_RE` rejects and `archive` cannot move, since it
# selects on a date they do not parse into -- aide-loop issue #76). The `assert
# warnings` guard below is what keeps "zero warnings" from passing vacuously.
#
# Re-pinned 2026-09-01 on the engine update 1.21.0 -> 1.28.1. The earlier
# baseline (four "status icon outside a structural status position" warnings
# and three `insights.md` entry-shape warnings) is gone because the engine
# retired both classes: 1.24.0 replaced the loose icon scan with the
# trailing-marker ownership rule, and 1.25.3 widened the insight-entry grammar
# so the queue/item-range provenances those three entries carry now parse
# (aide-loop issue #76). What the new engine reports instead is below; every
# one is an advisory about a pre-existing document state, not a regression:
#   - items 126 and 132 pin `docs/aide/progress.md` under Asserts against
#     (engine 1.23.0's always-authorised-path warning; both specs are merged
#     history, and `insights.md`'s open framework entries dated 2026-08-31
#     record the defect it names),
#   - three `progress.md` deliverable bullets reference items only mid-prose,
#     so under the marker rule they track nothing (engine 1.24.0),
#   - queues 002 and 004 are marked completed while `progress.md` still holds
#     open items for them.
# The first and third shapes carry a path but no line number
# (`items/NNN-x.md: text`), which `_FILE_SCOPED_WARNING_RE` keys the same way.
_PINNED_BASELINE_WARNINGS = Counter(
    {
        (
            "items/126-execute-the-golden-retirement.md",
            "'docs/aide/progress.md' is pinned under Asserts against, but every item "
            "is authorised to edit it — the status flip and the insight append are "
            "loop bookkeeping — so the pin can never hold and `aide scope` will "
            "report a contradiction on every run; put the read-only content check "
            "in an acceptance criterion's test instead",
        ): 1,
        (
            "items/132-judge-monotonicity-against-the-traversal-ordered-fit.md",
            "'docs/aide/progress.md' is pinned under Asserts against, but every item "
            "is authorised to edit it — the status flip and the insight append are "
            "loop bookkeeping — so the pin can never hold and `aide scope` will "
            "report a contradiction on every run; put the read-only content check "
            "in an acceptance criterion's test instead",
        ): 1,
        (
            "progress.md",
            "deliverable bullet references item(s) 024, 103, 110 but ends with no "
            "*(Item NNN)* marker — only the trailing marker ties an item to a "
            "bullet, so this bullet tracks nothing and those items read as "
            "untracked. End it with the marker (e.g. '. *(Item 024)*').",
        ): 1,
        (
            "progress.md",
            "deliverable bullet references item(s) 100 but ends with no "
            "*(Item NNN)* marker — only the trailing marker ties an item to a "
            "bullet, so this bullet tracks nothing and those items read as "
            "untracked. End it with the marker (e.g. '. *(Item 100)*').",
        ): 1,
        (
            "progress.md",
            "deliverable bullet references item(s) 103, 104 but ends with no "
            "*(Item NNN)* marker — only the trailing marker ties an item to a "
            "bullet, so this bullet tracks nothing and those items read as "
            "untracked. End it with the marker (e.g. '. *(Item 103)*').",
        ): 1,
        (
            "queue-002.md",
            "marked completed but still has open items in progress.md",
        ): 1,
        (
            "queue-004.md",
            "marked completed but still has open items in progress.md",
        ): 1,
    }
)

#: Splits `path:lineno: text` into the parts the baseline keys on and the one
#: it deliberately discards. The path may itself contain no colon (it is a
#: POSIX relative path rendered by the engine with `.as_posix()`), and the text
#: may contain any number of them, so only the first two fields are bounded.
_LOCATION_WARNING_RE = re.compile(r"^([^:]+):(\d+): (.*)$", re.DOTALL)

#: The engine's file-scoped shape, `path.md: text`, for a warning about a whole
#: document rather than one line of it (engine 1.23.0's spec-time advisories
#: and the queue-completion warning). Keyed identically to the located shape;
#: there is no line number to discard.
_FILE_SCOPED_WARNING_RE = re.compile(r"^([^:\s]+\.md): (.*)$", re.DOTALL)

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

# Human-gate warnings (engine 1.13.0). These ARE location-based, but pinning
# one would be a category error: the warning reports a *person's* pending
# decision, so it is emitted precisely while the gate is unresolved and
# vanishes the moment someone runs `aide gate approve`. Pinning it would make
# this test fail on the approval -- exactly backwards. The gates are already
# surfaced by three CLI paths that need no help from here (`aide check` warns,
# `aide status` prints, `aide claim` refuses a blocked item by name), so this
# module only has to stop treating them as regressions.
_GATE_DECISION_WARNING_RES = (
    re.compile(r"^progress\.md:\d+: human gate \d+ \("),
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


def _baseline_key(warning: str):
    """``path:lineno: text`` -> ``(path, text)``, or ``None`` if it is excluded.

    The line number is dropped deliberately (see the note above the baseline).
    Returning ``None`` for an excluded warning keeps the three exclusion rules
    in one place instead of repeated at every call site.
    """
    if warning.startswith(_BRANCH_STATE_WARNING_PREFIXES):
        return None
    if any(pattern.match(warning) for pattern in _AGGREGATED_WARNING_RES):
        return None
    if any(pattern.match(warning) for pattern in _GATE_DECISION_WARNING_RES):
        return None
    match = _LOCATION_WARNING_RE.match(warning)
    if match is not None:
        return (match.group(1), match.group(3))
    match = _FILE_SCOPED_WARNING_RE.match(warning)
    assert match is not None, (
        f"unrecognised aide check warning shape (not location-based, not "
        f"file-scoped, not a branch-state warning): {warning!r}"
    )
    return (match.group(1), match.group(2))


def test_ac8_no_new_aide_check_warning_beyond_pinned_baseline():
    warnings = _aide_check_warnings()
    # A capture/plumbing failure must fail loudly, not silently pass an empty
    # loop: `aide check` always reports the baseline warnings on this branch.
    assert warnings, "run_checks returned no warnings at all -- expected the pinned baseline"
    observed = Counter(
        key for key in (_baseline_key(w) for w in warnings) if key is not None
    )
    # A multiset comparison, in the tolerating direction only: every observed
    # (path, text) must be known and must not outnumber its baseline entry.
    # Fewer is fine -- the baseline says what is tolerated, not what is owed.
    excess = observed - _PINNED_BASELINE_WARNINGS
    assert not excess, (
        "aide check produced warnings beyond the pinned baseline "
        f"(path, text -> how many more than allowed): {dict(excess)}"
    )


def test_ac8_baseline_key_discards_only_the_line_number():
    """The property that makes the baseline survive a document rewrite.

    Pinned directly rather than left implicit: the same warning about the same
    file must key identically no matter what line it lands on, which is what
    each of the three recorded shifts violated under the old location key.
    """
    text = "status icon ✅ outside a structural status position"
    assert _baseline_key(f"progress.md:365: {text}") == ("progress.md", text)
    assert _baseline_key(f"progress.md:1: {text}") == ("progress.md", text)
    assert _baseline_key(f"progress.md:999999: {text}") == ("progress.md", text)
    # ...but the file and the text still discriminate.
    assert _baseline_key(f"queue/queue-002.md:80: {text}") != ("progress.md", text)
    assert _baseline_key("progress.md:365: something else entirely") != (
        "progress.md",
        text,
    )


def test_ac8_baseline_counts_catch_one_more_of_an_already_known_warning():
    """A set-keyed baseline would accept a repeat of a tolerated warning forever.

    The regression this guards is silent: a second document falling into an
    already-tolerated state produces a warning byte-identical to one that is
    already pinned, so only the multiset count can see it. Checked against
    every pinned key rather than one historical example (the three identical
    `insights.md` warnings that first motivated it no longer exist -- engine
    1.25.3 made those entries parse).
    """
    assert _PINNED_BASELINE_WARNINGS, "the baseline must pin something"
    for known, count in _PINNED_BASELINE_WARNINGS.items():
        assert not (Counter({known: count}) - _PINNED_BASELINE_WARNINGS)
        assert Counter({known: count + 1}) - _PINNED_BASELINE_WARNINGS == Counter(
            {known: 1}
        )


def test_ac8_file_scoped_warning_keys_on_path_and_text():
    """The engine's `path.md: text` shape (no line number) keys like the
    located shape, so a whole-document advisory can be pinned -- and an
    unknown one still fails the multiset rather than the shape assertion."""
    text = "'docs/aide/progress.md' is pinned under Asserts against, but ..."
    assert _baseline_key(f"items/126-x.md: {text}") == ("items/126-x.md", text)
    assert _baseline_key("queue-002.md: marked completed but still has open items") == (
        "queue-002.md",
        "marked completed but still has open items",
    )
    # A located warning is never mistaken for a file-scoped one.
    assert _baseline_key("progress.md:12: some text") == ("progress.md", "some text")


def test_ac8_baseline_excludes_the_three_documented_categories():
    """Each exclusion is a decision with a reason; pin that they still apply."""
    assert _baseline_key("stale claim branch aide/077-x for a finished item") is None
    assert _baseline_key("unrecognised branch aide/nonsense") is None
    assert _baseline_key(
        "32 item spec(s) have no mandatory '## Assumptions' block: 001, 002"
    ) is None
    assert _baseline_key(
        "progress.md:190: human gate 1 (Real segmenter output) is awaiting a decision"
    ) is None
