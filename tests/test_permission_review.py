"""Unit tests for the permission-review aggregator.

The module under test lives outside the package, at
``.claude/scripts/review_permissions.py`` (it is tooling for the AIDE workflow,
not part of ``segqc``), so it is loaded by path rather than imported normally.
We cover the three pure helpers: ``normalize_command``, ``correlate`` and
``is_covered`` — the logic the human review depends on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "scripts"
    / "review_permissions.py"
)
_spec = importlib.util.spec_from_file_location("review_permissions", _SCRIPT)
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)


# --- normalize_command ------------------------------------------------------


@pytest.mark.parametrize(
    "tool,detail,expected",
    [
        ("Bash", "git status -s", "Bash(git status:*)"),
        ("Bash", "gh pr view 5 --json state", "Bash(gh pr view:*)"),
        ("Bash", "python -m pytest tests/test_io.py", "Bash(python -m pytest:*)"),
        ("Bash", "python scripts/run.py", "Bash(python:*)"),
        ("Bash", "ls -la", "Bash(ls:*)"),
        ("Bash", "", "Bash"),
        ("Edit", "docs/aide/vision.md", "Edit(docs/aide/**)"),
        ("Write", "CLAUDE.md", "Write(CLAUDE.md)"),
        ("MultiEdit", "src/segqc/io.py", "Edit(src/segqc/**)"),
        ("Edit", r"docs\aide\roadmap.md", "Edit(docs/aide/**)"),
        ("WebFetch", "https://example.com/a/b", "WebFetch(domain:example.com)"),
        ("WebSearch", "how to do x", "WebSearch"),
    ],
)
def test_normalize_command(tool, detail, expected):
    assert review.normalize_command(tool, detail) == expected


# --- correlate --------------------------------------------------------------


def test_correlate_granted_when_completed_follows_request():
    records = [
        {"session_id": "s1", "event": "PreToolUse", "tool": "Bash", "detail": "git status"},
        {"session_id": "s1", "event": "PostToolUse", "tool": "Bash", "detail": "git status"},
    ]
    (call,) = review.correlate(records)
    assert call["outcome"] == "granted"


def test_correlate_denied_when_no_completion():
    records = [
        {"session_id": "s1", "event": "PreToolUse", "tool": "Bash", "detail": "gh pr create"},
    ]
    (call,) = review.correlate(records)
    assert call["outcome"] == "denied"


def test_correlate_pairs_one_to_one():
    # Two identical requests, only one completion -> one granted, one denied.
    records = [
        {"session_id": "s1", "event": "PreToolUse", "tool": "Bash", "detail": "git push"},
        {"session_id": "s1", "event": "PreToolUse", "tool": "Bash", "detail": "git push"},
        {"session_id": "s1", "event": "PostToolUse", "tool": "Bash", "detail": "git push"},
    ]
    outcomes = sorted(c["outcome"] for c in review.correlate(records))
    assert outcomes == ["denied", "granted"]


def test_correlate_isolates_sessions():
    # A completion in a different session must not satisfy the request.
    records = [
        {"session_id": "s1", "event": "PreToolUse", "tool": "Bash", "detail": "git push"},
        {"session_id": "s2", "event": "PostToolUse", "tool": "Bash", "detail": "git push"},
    ]
    (call,) = [c for c in review.correlate(records) if c["session_id"] == "s1"]
    assert call["outcome"] == "denied"


# --- is_covered -------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,detail,rules,expected",
    [
        ("Bash", "git status -s", ["Bash(git status:*)"], True),
        ("Bash", "git push --force", ["Bash(git status:*)"], False),
        ("Bash", "git statusx", ["Bash(git status:*)"], False),  # prefix boundary
        ("Read", "anything.py", ["Read", "Grep"], True),  # bare tool rule
        ("Edit", ".claude/skills/x/SKILL.md", ["Edit(.claude/skills/**)"], True),
        ("Edit", "src/segqc/io.py", ["Edit(.claude/skills/**)"], False),
        ("Bash", "gh pr create", ["Bash(git status:*)", "Read"], False),
    ],
)
def test_is_covered(tool, detail, rules, expected):
    assert review.is_covered(tool, detail, rules) is expected


# --- aggregate (integration of the three) -----------------------------------


def test_aggregate_classifies_and_ranks():
    calls = [
        {"session_id": "s", "tool": "Bash", "detail": "git status", "outcome": "granted"},
        {"session_id": "s", "tool": "Bash", "detail": "gh pr create 1", "outcome": "denied"},
        {"session_id": "s", "tool": "Bash", "detail": "gh pr create 2", "outcome": "denied"},
    ]
    rows = review.aggregate(calls, allow_rules=["Bash(git status:*)"], ask_rules=[])
    by_rule = {r["rule"]: r for r in rows}

    assert by_rule["Bash(git status:*)"]["status"] == "auto-allowed"
    new = by_rule["Bash(gh pr create:*)"]
    assert new["status"] == "new"
    assert new["total"] == 2 and new["denied"] == 2
    # 'new' bottlenecks sort ahead of already-covered rows.
    assert rows[0]["status"] == "new"
