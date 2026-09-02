#!/usr/bin/env python3
"""aide — the AIDE framework CLI.

A single, stdlib-only command-line tool for the deterministic parts of the AIDE
loop, so agents don't spend reasoning tokens on mechanical git/document surgery.
It is **venv-independent** (it must run before/without the project venv) and
**project-agnostic** — every project fact comes from ``aide.toml``.

Subcommands::

    python .aide/scripts/aide.py check [--queue NNN]   # consistency gate over docs/aide
    python .aide/scripts/aide.py scope [NNN]           # branch diff vs the item's authorised paths
    python .aide/scripts/aide.py progress set NNN <in-progress|in-review|done>
    python .aide/scripts/aide.py gate list|approve|decline [N]  # human gates in progress.md
    python .aide/scripts/aide.py queue start NNN       # create the queue branch (--specs for specs-)
    python .aide/scripts/aide.py queue tidy NNN        # mark a superseded queue as completed
    python .aide/scripts/aide.py insights list|tick|archive     # the insight inbox
    python .aide/scripts/aide.py claim [--queue NNN]   # pick + claim the next 📋 item
    python .aide/scripts/aide.py merge NNN [--base R]  # merge a validated item per git.mode
    python .aide/scripts/aide.py env                   # venv existence / import check + bootstrap
    python .aide/scripts/aide.py sync [--item NNN]     # preflight: fetch, clean-tree check, right branch
    python .aide/scripts/aide.py gc [--merged] [--yes] # delete claim branches whose work landed
    python .aide/scripts/aide.py status                # one-call roadmap-state report

The parsing/editing helpers are pure functions so they can be unit-tested without
touching git or the real filesystem (see ``.aide/scripts/tests``).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

# --------------------------------------------------------------------------- #
# Status icons (the format contract — see .aide/conventions.md)
# --------------------------------------------------------------------------- #
STATUS_TO_ICON = {
    "planned": "📋",
    "in-progress": "🚧",
    "in-review": "🔍",
    "complete": "✅",
    "deferred": "⏸️",
    "excluded": "❌",
}
ICON_TO_STATUS = {v: k for k, v in STATUS_TO_ICON.items()}
#: `in-review` sits between 🚧 and ✅ because it is strictly more advanced than
#: in-progress and strictly less than merged. It exists because ✅ used to mean
#: two different things depending on `git.mode`: under `auto-merge` the item was
#: merged, under `pr` it was pushed and awaiting a human — and everything
#: downstream read ✅ as "done", including the destructive sweep, which then
#: offered to delete the head branch of an open PR. **✅ now means merged, in
#: every mode**, and is set by `aide merge` when the merge actually happens.
RANK = {"planned": 0, "excluded": 1, "deferred": 2, "in-progress": 3,
        "in-review": 4, "complete": 5}
#: The statuses that still hold a dependent back. A dependency leaves the way
#: only by being merged (✅) or by leaving the queue's path (❌ excluded,
#: ⏸️ deferred) — 🚧 and 🔍 both block, because work in progress and work whose
#: PR is still open are alike missing from the base a dependent would branch
#: from. Named once because two separate decisions turn on it being the same
#: set: which item `aide claim` may offer, and whether a declared dependency
#: actually orders two specs (`queue_spec_findings`).
BLOCKING_STATUSES = ("planned", "in-progress", "in-review")

# Icons may be multi-codepoint (⏸️ = U+23F8 U+FE0F), so match by alternation
# (longest first), never a character class.
_ICON_ALT = "(?:" + "|".join(re.escape(i) for i in sorted(ICON_TO_STATUS, key=len, reverse=True)) + ")"
_ICON_RE = re.compile(_ICON_ALT)
# A deliverable bullet: leading "- " then a status icon.
_BULLET_RE = re.compile(r"^(?P<indent>\s*[-*]\s*)(?P<icon>" + _ICON_ALT + r")")
_CHECKBOX_RE = re.compile(r"^(?P<pre>\s*[-*]\s*\[)(?P<mark>[ xX])(?P<post>\].*)$")
_STAGE_HEADER_RE = re.compile(r"^##\s+Stage\s+(\d+)\b(.*)$")
_ANY_HEADER_RE = re.compile(r"^#{1,2}\s+")
# A stage header's status icon is the TRAILING icon only (the "— <icon>" tail);
# an icon inside the title text is plain text.
_TRAILING_ICON_RE = re.compile(r"(" + _ICON_ALT + r")\s*$")


# Every file this CLI reads is project-owned and hand-editable — aide.toml and the
# docs/aide/ living documents. Windows editors (Notepad, PowerShell's Out-File,
# "Save as UTF-8" in several IDEs) prepend a BOM, and a leading U+FEFF breaks
# first-line parsing *silently*: on the 3.9 fallback parser a BOM'd aide.toml loses
# only its FIRST table, because "^\[table\]$" fails on that one line while every
# later table still matches. [project] vanishes (source_dir back to its default)
# while [git] is honoured — a half-correct config, no error, every command
# reporting success. On 3.11 the same file raises an uncaught TOMLDecodeError.
# "utf-8-sig" strips a BOM when present and is byte-identical to "utf-8" when
# absent, so it is the correct default for anything a human may have touched.
_ENCODING = "utf-8-sig"


#: The accepted item-reference forms, as ONE definition (see conventions.md §1):
#:   *(Item 006)*            a single item
#:   *(Items 006, 044)*      a list — what create-queue tells authors to write
#:   *(Items 089/090)*       a list, slash-separated
#:   *(Items 071–075)*       an inclusive range, hyphen or en-dash
#: Everything that asks "does this line reference item NNN" goes through
#: _referenced_item_numbers, so the answer cannot differ between callers. It did
#: once: the status parse read only the FIRST number of a list, while the
#: progress-set matcher read any number literally present. Items after the first
#: were then orphaned — planned forever on a ✅ bullet, holding their queue open
#: and (since the live queue is the lowest-numbered open one) stranding
#: `aide claim` on a finished queue, while `aide progress set` acted on them
#: happily.
#: A number that opens a `YYYY-MM-DD` date is not an item number, and this is
#: the guard that says so. Without it the provenance shape AGENT-CONTEXT.md
#: itself prescribes — `*(item NNN, YYYY-MM-DD, engine X.Y.Z)*` — parsed as the
#: list `NNN, 2026, -08, -30`, and the unguarded `int()` below raised. The blast
#: radius was the whole verb, not the line: `aide progress set` reads every line
#: of progress.md, so four evidence annotations written in the documented
#: convention took `progress set` down for EVERY item repo-wide until a human
#: approved rewording them (issue #120).
#:
#: Two alternatives on purpose. `-\d{1,2}-\d{1,2}` recognises the date tail;
#: the bare `\d` forbids the backtrack that would otherwise let `\d+` give back
#: digits ("2026" → "202") until the tail no longer starts at the cursor and
#: the lookahead passed anyway. A range keeps working: "-092" carries one
#: hyphen group, not two.
_ITEM_REF_NOT_A_DATE = r"(?!\d|-\d{1,2}-\d{1,2})"
_ITEM_REF_NUM = r"0*\d+" + _ITEM_REF_NOT_A_DATE
_ITEM_REF_GROUP_RE = re.compile(
    r"[Ii]tems?\s+(" + _ITEM_REF_NUM + r"(?:\s*[,/–-]\s*" + _ITEM_REF_NUM + r")*)")
_ITEM_REF_SPLIT_RE = re.compile(r"\s*[,/]\s*")
_ITEM_REF_RANGE_RE = re.compile(r"^0*(\d+)\s*[–-]\s*0*(\d+)$")
#: The second, independent hardening: what the split hands back must LOOK like
#: an item number before it is read as one. Either fix alone stops the crash;
#: both are kept because the regex is a statement about one known prose shape
#: while this is the invariant — a part that is not a number is provenance
#: prose to skip, never a traceback out of an unrelated verb.
_ITEM_REF_NUMBER_RE = re.compile(r"^0*\d+$")

#: An inclusive range wider than this is treated as a typo and contributes only
#: its endpoints, so a stray "Items 6-9999" cannot invent thousands of items.
_ITEM_RANGE_MAX_SPAN = 50


def _referenced_item_numbers(text: str) -> List[int]:
    """Every item number referenced in ``text``, ranges expanded inclusively."""
    nums: List[int] = []
    for group in _ITEM_REF_GROUP_RE.finditer(text):
        for part in _ITEM_REF_SPLIT_RE.split(group.group(1)):
            part = part.strip()
            if not part:
                continue
            rng = _ITEM_REF_RANGE_RE.match(part)
            if rng is None:
                if _ITEM_REF_NUMBER_RE.match(part):
                    nums.append(int(part))
                continue
            lo, hi = int(rng.group(1)), int(rng.group(2))
            if lo <= hi <= lo + _ITEM_RANGE_MAX_SPAN:
                nums.extend(range(lo, hi + 1))
            else:
                nums.extend((lo, hi))
    return nums


def _has_typo_range(text: str) -> bool:
    """Does ``text`` carry a range so wide the reader treats it as a typo?

    `_referenced_item_numbers` keeps only such a range's ENDPOINTS, so what it
    hands back is deliberately not what the author wrote — `Items 044-999` reads
    as {44, 999}, and 999 is an artifact of the typo, not an item. That is a
    safe misreading while it stays in memory. It is not safe for a caller that
    writes the numbers back into the document, which is why the desugar asks.
    """
    for group in _ITEM_REF_GROUP_RE.finditer(text):
        for part in _ITEM_REF_SPLIT_RE.split(group.group(1)):
            rng = _ITEM_REF_RANGE_RE.match(part.strip())
            if rng is None:
                continue
            lo, hi = int(rng.group(1)), int(rng.group(2))
            if not lo <= hi <= lo + _ITEM_RANGE_MAX_SPAN:
                return True
    return False


def _references_item(text: str, num: int) -> bool:
    """Does ``text`` reference item ``num`` in any accepted form?"""
    return num in _referenced_item_numbers(text)


#: The item-reference MARKER that closes a deliverable bullet —
#: `- 📋 <text>. *(Item 006)*` — the `*(…)*` suffix the templates prescribe
#: (§1 → progress.md calls it "the *(Item NNN)* suffix"). Only this trailing
#: marker ties items to the bullet: a reference elsewhere in the bullet's prose
#: ("absorbing *(Item 095)*'s scope") is free text and attributes nothing
#: (issue #99). Several adjacent markers at the end all count, and a trailing
#: period after the last one is tolerated.
_BULLET_MARKER_RE = re.compile(
    r"(?:\*\(\s*[Ii]tems?\s+[^)\n]*\)\*[ \t.]*)+$")


def _bullet_marker_item_numbers(last_line: str) -> List[int]:
    """Item numbers in the trailing marker of a bullet's final line, if any."""
    m = _BULLET_MARKER_RE.search(last_line)
    return _referenced_item_numbers(m.group(0)) if m else []


def _deliverable_bullet_spans(lines: List[str]) -> List[Tuple[int, int]]:
    """``(first, last)`` line indices of each deliverable bullet.

    A deliverable bullet is a ``_BULLET_RE`` line plus its wrapped continuation
    lines — indented text carrying no bullet marker of its own. A blank line, a
    non-deliverable bullet, or an unindented new block ends the span. This is
    the ONE definition of a bullet's extent; ``_parse_item_status`` (read) and
    ``set_item_status`` (write) both build on it, so "which bullet owns item
    NNN" cannot differ between the two directions.
    """
    spans: List[Tuple[int, int]] = []
    open_span = False
    for i, line in enumerate(lines):
        if _BULLET_RE.match(line):
            spans.append((i, i))
            open_span = True
        elif not line.strip() or re.match(r"^\s*[-*]\s", line) or not re.match(r"^\s+\S", line):
            open_span = False
        elif open_span:
            spans[-1] = (spans[-1][0], i)
    return spans


# --------------------------------------------------------------------------- #
# TOML config (tomllib on 3.11+, tiny fallback for the aide.toml subset on 3.9)
# --------------------------------------------------------------------------- #
DEFAULT_CONFIG: Dict[str, Dict[str, object]] = {
    "project": {"name": "project", "source_dir": "src", "tests_dir": "tests", "docs_dir": "docs/aide"},
    "python": {"venv": ".venv", "bootstrap": "pip install -e .[dev]",
               "test_command": "python -m pytest", "import_check": ""},
    "git": {"mode": "auto-merge", "main_branch": "main", "branch_prefix": "aide/"},
    "loop": {"queue_cap": 10, "validation_rounds": 3, "clarify": "assume",
             "claim_scope": "live-queue"},
    "framework": {"repo": ""},
    # [validation] — named environment profiles for stage-validation items:
    # <name> = <python expression>, true iff the environment provides the
    # capability (e.g. gpu = "__import__('torch').cuda.is_available()").
    "validation": {},
}


# Escape sequences this reader decodes inside a basic (double-quoted) string. TOML
# also defines \b \t \n \f \r \uXXXX \UXXXXXXXX; rather than half-implement them and
# quietly disagree with tomllib, an unlisted escape is a ConfigError (see below).
_BASIC_ESCAPES = {'"': '"', "\\": "\\"}


def _read_quoted_value(key: str, stripped: str, lineno: int) -> str:
    """Decode the quoted string at the start of ``stripped``, or raise ``ConfigError``.

    Finding where a string ENDS and extracting what it CONTAINS are the same scan, so
    they live in one function. Splitting them is what produced the bug this replaces:
    the validator walked the value escape-aware while the extractor used a naive
    ``split(quote, 1)[0]``, so ``msg = "he said \\"hi\\""`` passed validation and was
    then silently truncated to ``he said \\``.

    Single-quoted strings are TOML *literal* strings: no escapes, backslash is itself.
    Double-quoted are *basic* strings, where a backslash escapes the next character.
    """
    quote = stripped[0]
    out: List[str] = []
    i = 1
    while i < len(stripped):
        ch = stripped[i]
        if quote == '"' and ch == "\\":
            nxt = stripped[i + 1] if i + 1 < len(stripped) else ""
            if not nxt:
                raise ConfigError(
                    f"line {lineno}: unterminated escape in the value for key {key!r} — "
                    "a backslash at the end of a basic string escapes nothing"
                )
            if nxt not in _BASIC_ESCAPES:
                raise ConfigError(
                    f"line {lineno}: unsupported escape '\\{nxt}' in the value for "
                    f"key {key!r} — this minimal reader decodes only \\\\ and \\\"; "
                    f"use a single-quoted 'literal string' (backslashes are literal "
                    f"there) or forward slashes"
                )
            out.append(_BASIC_ESCAPES[nxt])
            i += 2
            continue
        if ch == quote:
            tail = stripped[i + 1:].lstrip()
            if tail and not tail.startswith("#"):
                raise ConfigError(
                    f"line {lineno}: trailing characters after the quoted value for "
                    f"key {key!r}: {tail!r}"
                )
            return "".join(out)
        out.append(ch)
        i += 1

    raise ConfigError(
        f"line {lineno}: unterminated string for key {key!r} — "
        f"the value opens with {quote} but never closes it"
    )


class ConfigError(Exception):
    """``aide.toml`` cannot be trusted — malformed, so its facts are unknowable.

    Raised instead of guessing. Every project fact the framework acts on comes from
    that file, so silently falling back to defaults would scope the builder at the
    wrong directory, pick the wrong git mode, or run the wrong test command while
    reporting success. ``main`` catches this and prints it as a plain error.
    """


def _parse_toml(text: str) -> Dict[str, Dict[str, object]]:
    """Minimal TOML reader for the flat ``[table] key = value`` shape of aide.toml.

    Supports string/int/float/bool scalars and ``#`` comments. Used only when the
    stdlib ``tomllib`` (Python 3.11+) is unavailable, so the CLI and its tests run
    on the project's 3.9 venv too.

    Deliberately lenient about what it *ignores* (unknown lines, blank tables) but
    strict about what it would otherwise *misread*, because a wrong-but-plausible
    value is worse than a refusal: an unterminated quoted string used to yield the
    truncated text, so a typo became a believable answer on 3.9 while 3.11's tomllib
    rejected the same file. Quoted values are decoded by ``_read_quoted_value``,
    which raises ``ConfigError`` rather than guess — so both parser paths agree on
    which files are readable.
    """
    data: Dict[str, Dict[str, object]] = {}
    table: Optional[Dict[str, object]] = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([A-Za-z0-9_.]+)\]$", line)
        if m:
            table = data.setdefault(m.group(1), {})
            continue
        if table is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # A quoted value owns everything up to its closing quote — a '#' inside it is
        # data, not a comment — so it is scanned before any comment stripping. Only
        # an UNquoted value is truncated at '#'.
        if value and value[0] in "\"'":
            table[key] = _read_quoted_value(key, value, lineno)
            continue
        token = value.split("#", 1)[0].strip()
        if not token:
            raise ConfigError(f"line {lineno}: missing value for key {key!r}")
        if token.lower() in ("true", "false"):
            table[key] = token.lower() == "true"
        else:
            try:
                table[key] = int(token)
            except ValueError:
                try:
                    table[key] = float(token)
                except ValueError:
                    table[key] = token
    return data


def _config_error(path: Path, what: str, exc: object) -> "ConfigError":
    """One phrasing for every way ``aide.toml`` can fail, so they cannot drift.

    ``what`` distinguishes the causes a reader would act on differently: a file that
    ``is malformed`` needs an edit, one that ``cannot be read`` needs permissions or
    disk attention. The rest — naming the path, and why defaults are not an
    acceptable fallback — is identical in every case.
    """
    return ConfigError(
        f"{path} {what}: {exc}\n"
        f"  aide.toml states this project's facts (source_dir, git mode, test "
        f"command); refusing to continue with defaults that would be silently wrong."
    )


def load_config(repo_root: Path) -> Dict[str, Dict[str, object]]:
    """Load ``aide.toml`` merged over defaults.

    A *missing* file is fine — defaults apply, which is what an unconfigured repo
    means. A *malformed* file is not: it states project facts that cannot be read,
    so this raises ``ConfigError`` naming the file rather than falling back to
    defaults that would silently be wrong.
    """
    merged = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    path = repo_root / "aide.toml"
    if path.is_file():
        try:
            text = path.read_text(encoding=_ENCODING)
        except UnicodeDecodeError as exc:
            raise _config_error(path, "is malformed", exc) from exc
        except OSError as exc:
            # Present but unreadable (permissions, a device error, a dangling
            # link). The file may be perfectly well-formed — say so accurately
            # rather than sending the reader to hunt for a syntax mistake.
            raise _config_error(path, "cannot be read", exc) from exc
        try:
            import tomllib  # type: ignore
        except ModuleNotFoundError:
            detail_source = _parse_toml
        else:
            # tomllib.TOMLDecodeError subclasses ValueError; catching ValueError
            # keeps this working if that relationship ever changes.
            detail_source = tomllib.loads
        try:
            parsed = detail_source(text)
        except (ConfigError, ValueError) as exc:
            # Both parsers report line/column but neither knows the path, and the
            # path is the one thing a reader needs to go fix it.
            raise _config_error(path, "is malformed", exc) from exc
        for section, values in parsed.items():
            merged.setdefault(section, {})
            if isinstance(values, dict):
                merged[section].update(values)
    return merged


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up from ``start`` (default cwd) to the directory holding aide.toml."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "aide.toml").is_file():
            return candidate
    return start


def docs_dir(repo_root: Path, config: Dict[str, Dict[str, object]]) -> Path:
    return repo_root / str(config["project"].get("docs_dir", "docs/aide"))


# --------------------------------------------------------------------------- #
# progress.md — parsing helpers
# --------------------------------------------------------------------------- #
def _icon_status(text: str) -> Optional[str]:
    m = _ICON_RE.search(text)
    return ICON_TO_STATUS[m.group(0)] if m else None


def _header_status(line: str) -> Optional[str]:
    """A stage header's status — its trailing icon only."""
    m = _TRAILING_ICON_RE.search(line)
    return ICON_TO_STATUS[m.group(1)] if m else None


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _structural_status(line: str) -> Optional[str]:
    """Status conveyed by a line's STRUCTURAL icon position only.

    Structural positions (the format contract, conventions.md §1): the leading
    icon of a deliverable bullet, a table row's Status (last) cell, and a stage
    header's trailing icon. An icon anywhere else on a line is plain text and
    is never read as status — prose stays free of the icon vocabulary.
    """
    m = _BULLET_RE.match(line)
    if m:
        return ICON_TO_STATUS[m.group("icon")]
    if line.strip().startswith("|"):
        cells = _split_row(line)
        return _icon_status(cells[-1]) if cells else None
    if _STAGE_HEADER_RE.match(line):
        return _header_status(line)
    return None


def stage_sections(lines: List[str]) -> List[Tuple[int, int, str]]:
    """Return ``(start_index, end_index_exclusive, stage_number)`` per stage section."""
    out: List[Tuple[int, int, str]] = []
    starts: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _STAGE_HEADER_RE.match(line)
        if m:
            starts.append((i, m.group(1)))
    for idx, (start, num) in enumerate(starts):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if _ANY_HEADER_RE.match(lines[j]):
                end = j
                break
        out.append((start, end, num))
    return out


def stage_deliverable_statuses(lines: List[str], start: int, end: int) -> List[str]:
    """Statuses of the flat deliverable bullets within a stage section."""
    statuses: List[str] = []
    for line in lines[start:end]:
        if _CHECKBOX_RE.match(line):
            continue
        m = _BULLET_RE.match(line)
        if m:
            statuses.append(ICON_TO_STATUS[m.group("icon")])
    return statuses


def rollup_status(statuses: List[str]) -> Optional[str]:
    """Derive a stage status from its deliverable statuses (None if no bullets)."""
    if not statuses:
        return None
    if all(s in ("complete", "deferred", "excluded") for s in statuses) and any(
        s == "complete" for s in statuses
    ):
        return "complete"
    # 🔍 is deliberately absent from the set above: an item awaiting review has
    # not landed, so a stage holding one is 🚧, never ✅. That is the whole point
    # of the state — a `pr`-mode run must not roll a stage up to "shipped" on
    # work that is still an open PR.
    if any(s in ("complete", "in-progress", "in-review") for s in statuses):
        return "in-progress"
    return "planned"


# --------------------------------------------------------------------------- #
# Outcome targets (optional table — see conventions.md §1)
# --------------------------------------------------------------------------- #
_TARGETS_HEADING_RE = re.compile(r"^#{1,2}\s+Outcome targets\b", re.IGNORECASE)
#: Table-local status vocabulary (like the env-gated verification table's):
#: the cell's LEADING mark decides, the rest is evidence/notes for humans.
_TARGET_STATUS_KIND = {"✅": "met", "❌": "not-met", "❓": "unverified"}


class OutcomeTarget(NamedTuple):
    lineno: int              # 1-based line number in progress.md
    text: str                # the Target cell
    objectives: List[str]    # G-codes named in the Objective cell
    kind: Optional[str]      # "met" | "not-met" | "unverified" | None (unrecognised)


#: The optional `## Human gates` table — a decision only a person can make,
#: blocking work until they make it. Kept separate from acceptance boxes
#: deliberately: conventions.md §1 defines those as observable checks OF THE
#: BUILT THING, which a steering decision is not. Same reasoning that gave
#: Outcome targets their own table rather than overloading the checkboxes.
_GATES_HEADING_RE = re.compile(r"^#{1,2}\s+Human gates\b", re.IGNORECASE)
#: Table-local vocabulary, like Outcome targets': the LEADING mark decides.
_GATE_STATUS_KIND = {"⏳": "awaiting", "✅": "approved", "❌": "declined"}
#: A gate whose Blocks cell says this halts every item, everywhere — for a
#: programme-level decision ("no work proceeds until sign-off").
_GATE_BLOCKS_ALL = "all"
#: `stage N` — every item the named stage's deliverables reference. Blocking is
#: tied to a STAGE, never to a queue: a queue is an incidental batch boundary
#: (part of a stage, a stage, or several small ones), so "the live queue" names
#: different work from one week to the next while the decision has not changed.
#: A stage is the roadmap's own unit and means the same thing over time.
_GATE_BLOCKS_STAGE_RE = re.compile(r"^stage\s+0*(\d+)$", re.IGNORECASE)


class HumanGate(NamedTuple):
    lineno: int              # 1-based line number in progress.md
    text: str                # the Gate cell
    blocks: List[int]        # item numbers named directly (empty for stage/all)
    stage: Optional[str]     # stage number when the cell reads "stage N"
    blocks_all: bool         # True when the cell reads "all"
    kind: Optional[str]      # "awaiting" | "approved" | "declined" | None

    @property
    def reach(self) -> str:
        """How far this gate reaches, for a human-readable report."""
        if self.blocks_all:
            return "all items"
        if self.stage is not None:
            return f"stage {self.stage}"
        return ("items " + ", ".join(f"{i:03d}" for i in self.blocks)
                if self.blocks else "nothing named")


def stage_section(lines: List[str], stage: str) -> Optional[Tuple[int, int, str]]:
    """The stage section numbered *stage*, or None if no such section exists.

    The single place the "which section is stage N" lookup lives. Callers need
    to tell "no such stage" from "the stage is there and empty" — an absent
    section is a typo, an empty one is a stage nobody has queued work for yet —
    and a helper that collapses both into a falsy return makes that
    indistinguishable at every call site.
    """
    return next((sec for sec in stage_sections(lines)
                 if _same_stage(sec[2], stage)), None)


def stage_item_numbers(lines: List[str], stage: str) -> List[int]:
    """Item numbers referenced by *stage*'s deliverable bullets in progress.md.

    Reuses the §1 rule that only a deliverable bullet (and its wrapped
    continuation lines) carries an item reference, so a Notes cell or an
    acceptance checkbox naming an item does not widen a stage gate's reach.

    Empty for a stage that does not exist *and* for one whose deliverables name
    no item yet; ``stage_section`` is what separates the two.
    """
    section = stage_section(lines, stage)
    if section is None:
        return []
    start, end, _ = section
    return sorted(_parse_item_status(lines[start:end])[2])


def _blocked_item_numbers(cell: str) -> List[int]:
    """Item numbers in a gate's ``Blocks`` cell.

    Accepts the §1 reference forms (``Items 106, 110–112``) *and* the bare
    numbers an author naturally writes in a column already headed "Blocks"
    (``106``, ``110, 111``). The shared extractor keys off the word "Item", so
    a bare list would parse as **nothing** — and a gate blocking nothing is a
    gate that silently does not work, the one failure mode this table exists to
    prevent. Normalising the cell first reuses that extractor's list/range
    handling rather than growing a second dialect.
    """
    text = cell if re.search(r"\bitems?\b", cell, re.IGNORECASE) else f"Items {cell}"
    return _referenced_item_numbers(text)


def human_gates(lines: List[str]) -> List[HumanGate]:
    """Rows of the optional ``## Human gates`` table in progress.md.

    A gate is a decision only a person can make — approving a direction,
    signing off an irreversible change, confirming an out-of-band prerequisite
    arrived. It blocks work until resolved, and **no agent may resolve one**:
    that is the entire point, and the reason the state lives in a CLI-written
    table rather than a checkbox any role could tick.

    ``Blocks`` accepts the item-reference forms of §1 (``106``, ``106, 107``,
    ``106–108``), ``stage N`` for every item that stage's deliverables
    reference, or ``all`` for a programme-level stop.
    """
    out: List[HumanGate] = []
    in_section = False
    for i, line in enumerate(lines):
        if _GATES_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break  # next section — the table is over
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if _is_gate_table_furniture(cells) or len(cells) != 4:
            continue
        kind = next((k for icon, k in _GATE_STATUS_KIND.items()
                     if cells[2].startswith(icon)), None)
        blocks_cell = cells[1].strip()
        blocks_all = blocks_cell.lower() == _GATE_BLOCKS_ALL
        sm = _GATE_BLOCKS_STAGE_RE.match(blocks_cell)
        stage = sm.group(1) if sm else None
        blocks = [] if (blocks_all or stage) else _blocked_item_numbers(blocks_cell)
        out.append(HumanGate(i + 1, cells[0], blocks, stage, blocks_all, kind))
    return out


def blocking_gates(lines: List[str]) -> List[HumanGate]:
    """Gates still holding work up — every gate that is not ``✅ Approved``.

    **A declined gate keeps blocking.** It is *resolved* — a person decided —
    but the decision was "no", so releasing the work it guards would run
    exactly what was refused. The remedy is to re-plan (drop the item, or
    change what the gate asks), not to let the loop proceed. Only approval
    opens a gate.

    An unrecognised status also blocks: a typo in the mark must not silently
    open one.
    """
    return [g for g in human_gates(lines) if g.kind != "approved"]


def gate_blocked_items(lines: List[str]) -> Tuple[set, List[HumanGate]]:
    """``(blocked item numbers, block-everything gates)`` from the blocking gates.

    A ``stage N`` gate resolves through progress.md to the items that stage's
    deliverables reference, so its reach follows the roadmap as the stage's
    contents change — which is the whole reason reach is anchored to a stage
    rather than to whichever queue happens to be live.
    """
    blocked, everything = set(), []
    for g in blocking_gates(lines):
        if g.blocks_all:
            everything.append(g)
        elif g.stage is not None:
            blocked.update(stage_item_numbers(lines, g.stage))
        else:
            blocked.update(g.blocks)
    return blocked, everything


def outcome_targets(lines: List[str]) -> List[OutcomeTarget]:
    """Rows of the optional ``## Outcome targets`` table in progress.md.

    An outcome target is a MEASURED result the roadmap commits to (an error
    rate, a benchmark) — something shipped work can enable but never guarantee,
    so it is deliberately outside the stage rollup: a stage's ✅ keeps meaning
    "the planned work shipped", and goal truth lives here, gating the
    OBJECTIVE rows instead (an objective linked to a target that is not
    ``✅ Met`` cannot roll up to ✅).
    """
    out: List[OutcomeTarget] = []
    in_section = False
    for i, line in enumerate(lines):
        if _TARGETS_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break  # next section — the table is over
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        # Skip anything but a data row: wrong arity, the header row, the
        # separator row (only -/:), or an empty Target cell.
        if len(cells) != 5 or cells[0].lower() == "target" or set(cells[0]) <= set("-: "):
            continue
        kind = next((k for icon, k in _TARGET_STATUS_KIND.items()
                     if cells[3].startswith(icon)), None)
        out.append(OutcomeTarget(i + 1, cells[0], re.findall(r"G\d+", cells[1]), kind))
    return out


# --------------------------------------------------------------------------- #
# progress.md — editing
# --------------------------------------------------------------------------- #
def _replace_first_icon(line: str, status: str) -> str:
    return _ICON_RE.sub(STATUS_TO_ICON[status], line, count=1)


def _sub_status_cell(line: str, status: str) -> str:
    """Replace the icon in a table row's Status (last) cell only.

    Icons in other cells (a title, an objective description) are plain text and
    must survive the edit untouched.
    """
    head, sep, tail = line.rpartition("|")
    if sep:
        body, sep2, cell = head.rpartition("|")
        if sep2:
            return body + "|" + _ICON_RE.sub(STATUS_TO_ICON[status], cell, count=1) + "|" + tail
    return _ICON_RE.sub(STATUS_TO_ICON[status], line, count=1)


def _set_summary_row(lines: List[str], stage_num: str, status: str) -> None:
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if len(cells) == 4 and cells[0] == stage_num and _icon_status(cells[3]):
            current = _icon_status(cells[3])
            if current in ("deferred", "excluded"):
                return
            if RANK[status] >= RANK[current]:
                lines[i] = _sub_status_cell(line, status)
            return


def _set_stage_header(lines: List[str], start: int, status: str) -> None:
    line = lines[start]
    current = _header_status(line)
    if current in ("deferred", "excluded"):
        return
    if current is None:
        lines[start] = line.rstrip() + f" — {STATUS_TO_ICON[status]}"
    elif RANK[status] >= RANK[current]:
        lines[start] = _TRAILING_ICON_RE.sub(STATUS_TO_ICON[status], line)


def _same_stage(a: str, b: str) -> bool:
    """Compare two stage numbers, ignoring zero-padding when both are numeric."""
    sa, sb = str(a).strip(), str(b).strip()
    if sa.isdigit() and sb.isdigit():
        return int(sa) == int(sb)
    return sa == sb


def acceptance_boxes(lines: List[str], start: int, end: int) -> List[int]:
    """Line indices of the acceptance checkboxes in one stage section, in order.

    An acceptance box is an *attestation*: a human states that an observable
    criterion holds. It is deliberately not derived from anything — the rollup
    skips checkbox lines (see ``stage_deliverable_statuses``), no ``aide check``
    rule gates a ✅ stage on them, and nothing else reads them. That is why
    ``set_item_status`` no longer ticks them as a side effect of a status
    change: a rollup cannot attest, and auto-ticking made the honest state
    "shipped, but this criterion is not met" impossible to keep — the same
    state Outcome targets exist to express at the objective level.

    Ticking now goes through ``aide progress accept``, which is deliberate,
    logged, and cannot be undone by an unrelated item's status change.
    """
    return [i for i in range(start, end) if _CHECKBOX_RE.match(lines[i])]


def accept_criteria(text: str, stage: str, criteria: Optional[List[int]],
                    evidence: Optional[str] = None) -> Tuple[str, List[str]]:
    """Tick acceptance boxes in *stage*; return (updated text, messages).

    ``criteria`` is a list of 1-based box indices, or None for every box in the
    stage. An already-ticked box is reported and left alone rather than being
    silently counted as newly accepted. Raises ``ValueError`` when the stage or
    an index does not exist — a typo'd stage must not pass as a no-op.

    The stage is matched numerically, so ``accept 6`` finds a section headed
    ``## Stage 06`` — ``stage_sections`` reports the header text verbatim, and
    a caller typing the correct number should not have to guess its padding.
    """
    lines = text.splitlines()
    section = stage_section(lines, stage)
    if section is None:
        raise ValueError(f"no Stage {stage} section in progress.md")
    start, end, _ = section
    boxes = acceptance_boxes(lines, start, end)
    if not boxes:
        raise ValueError(f"Stage {stage} has no acceptance checkboxes")
    wanted = list(range(1, len(boxes) + 1)) if criteria is None else criteria
    for n in wanted:
        if not 1 <= n <= len(boxes):
            raise ValueError(
                f"Stage {stage} has {len(boxes)} acceptance criteria; {n} is out of range")
    messages: List[str] = []
    for n in wanted:
        i = boxes[n - 1]
        m = _CHECKBOX_RE.match(lines[i])
        if m.group("mark") != " ":
            messages.append(f"criterion {n}: already ticked, unchanged")
            continue
        post = m.group("post")
        if evidence:
            post = post.rstrip() + f" *({evidence})*"
        lines[i] = m.group("pre") + "x" + post
        messages.append(f"criterion {n}: accepted")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), messages


def _objective_stages(delivered_by: str) -> List[str]:
    return re.findall(r"\bStage[s]?\s+([\d,\s]+)", delivered_by)


def _apply_objective_rollup(lines: List[str], stage_status: Dict[str, str]) -> None:
    # An objective linked to an outcome target that is not ✅ Met can never
    # roll up to ✅: its stages shipping is necessary but not sufficient.
    blocked = {g for t in outcome_targets(lines) if t.kind != "met"
               for g in t.objectives}
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        gm = re.match(r"G\d+", cells[0]) if len(cells) == 3 else None
        if gm and _icon_status(cells[2]):
            nums: List[str] = []
            for chunk in re.findall(r"\d+", cells[1]):
                nums.append(chunk)
            if not nums:
                continue
            current = _icon_status(cells[2])
            if current in ("deferred", "excluded"):
                continue
            statuses = [stage_status.get(n) for n in nums if stage_status.get(n)]
            if statuses and all(s == "complete" for s in statuses):
                derived = "complete"
            elif any(s in ("complete", "in-progress", "in-review") for s in statuses):
                derived = "in-progress"
            else:
                derived = current
            if derived == "complete" and gm.group(0) in blocked:
                derived = "in-progress"
            if RANK[derived] >= RANK[current]:
                lines[i] = _sub_status_cell(line, derived)


def _spec_stage_and_title(repo_root: Path, config, number: int) -> Tuple[Optional[str], Optional[str]]:
    """(stage, title) from the item's spec header, best effort."""
    idir = docs_dir(repo_root, config) / "items"
    specs = item_spec_paths(idir, number)
    if not specs:
        return None, None
    text = specs[0].read_text(encoding=_ENCODING)
    tm = re.search(r"^#\s+Item\s+0*" + str(number) + r"\s*[—–-]\s*(.+?)\s*$", text, re.MULTILINE)
    sm = re.search(r"\*\*Stage:\*\*\s*(\d+)", text)
    return (sm.group(1) if sm else None), (tm.group(1) if tm else None)


def insert_item_reference(text: str, number: int, stage: str, title: str) -> Optional[str]:
    """Append a planned deliverable bullet for item ``number`` to the given
    stage's Deliverables block (used when a queue back-fill was missed, so
    ``progress set`` can self-heal instead of hard-erroring). Returns the
    updated text, or None when the stage section / Deliverables block is
    missing — that stays a loud error."""
    lines = text.splitlines()
    for start, end, snum in stage_sections(lines):
        if snum != str(stage):
            continue
        insert_at = next((i + 1 for i in range(start, end)
                          if lines[i].strip().startswith("**Deliverables")), None)
        # After the last bullet's WHOLE span, continuations included. Icon
        # line + 1 used to split a wrapped bullet in two — cosmetic while any
        # reference on any line attributed, but under the trailing-marker rule
        # (issue #99) the split strands the new bullet's marker mid-span and
        # hands the wrapped bullet's marker to the wrong owner.
        spans = _deliverable_bullet_spans(lines[start:end])
        if spans:
            insert_at = start + spans[-1][1] + 1
        if insert_at is None:
            return None
        lines.insert(insert_at, f"- 📋 {title}. *(Item {number:03d})*")
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return None


def _split_multi_item_bullets(lines: List[str], num: int, status: str) -> List[str]:
    """One bullet, one item: desugar a bullet that owns ``num`` *and* siblings.

    A trailing marker may name several items — ``*(Items 016, 017)*``, the form
    §1 → progress.md blesses and `/aide-create-queue` step 8 recommends — but a
    bullet carries ONE icon, and that icon is the status cell. So flipping the
    bullet for 016 also completed 017: never specced, never built, thereafter
    read as ✅ by everything that parses the file, and silently discounted from
    its queue's open count (issue #131). The engine's own writer had already
    modelled one item per bullet — `insert_item_reference` appends a singular
    marker — so the shape it told authors to write was one its status machinery
    could not represent.

    The form stays legal and desugars here: the bullet becomes one bullet per
    item, same text, one ``*(Item NNN)*`` each, in the marker's order. The item
    being flipped then moves alone and its siblings keep the status they had —
    the sibling protection issue #99 gave a prose mention, given to the list
    form that actually attributes.

    Only a flip that would ADVANCE the bullet splits it. A `progress set` that
    changes nothing must rewrite nothing: re-running one, or setting a status
    the bullet already holds, is not a reason to reshape a consumer's file.
    """
    for start, last in reversed(_deliverable_bullet_spans(lines)):
        marker = _BULLET_MARKER_RE.search(lines[last])
        if marker is None:
            continue
        nums = list(dict.fromkeys(_referenced_item_numbers(marker.group(0))))
        if num not in nums or len(nums) < 2:
            continue
        # A range wider than the typo limit contributes only its endpoints, so
        # `nums` is not what the author wrote: `*(Items 044-999)*` would grow a
        # bullet for a phantom item 999, indistinguishable from a real one and
        # thereafter counted by `check`, `claim` and every queue rollup. Writing
        # fiction into the tracked document is worse than the shared cell this
        # function exists to remove, so a malformed marker keeps the old
        # behaviour and this leaves it exactly as the author typed it.
        #
        # Whole-bullet, deliberately: in `*(Items 006, 044-999)*` the sound half
        # keeps the shared cell too. Splitting the good elements while preserving
        # the malformed one is a lot of machinery for a marker whose own author
        # has already mistyped it, and the loud version — refusing the flip — is
        # worse, since it would strand a real item behind a typo in prose.
        if _has_typo_range(marker.group(0)):
            continue
        current = ICON_TO_STATUS[_BULLET_RE.match(lines[start]).group("icon")]
        if not current or RANK[status] <= RANK[current]:
            continue
        head = lines[last][:marker.start()]
        # Whatever followed the last `)*` — the sentence-ending period the
        # marker regex tolerates — belongs to every copy, not just the first.
        matched = marker.group(0)
        tail = matched[len(matched.rstrip(" \t.")):]
        block: List[str] = []
        for n in nums:
            copy = lines[start:last + 1]
            copy[-1] = f"{head}*(Item {n:03d})*{tail}"
            block.extend(copy)
        lines[start:last + 1] = block
    return lines


def set_item_status(text: str, num: int, status: str) -> str:
    """Flip item NNN's deliverable bullet(s) to ``status`` and roll stages up.

    ``status`` is ``in-progress``, ``in-review`` or ``complete``. Updates summary/header/
    objective rows only for stages that fully complete. Never downgrades an
    existing status (additive log), and never touches an acceptance checkbox —
    those are human attestations, ticked only by ``aide progress accept``.

    A bullet whose marker names several items is split into one bullet per item
    first (see ``_split_multi_item_bullets``), so no sibling is carried along by
    a flip it did not earn.
    """
    lines = text.splitlines()
    # A marker naming several items is one status cell for all of them, so the
    # bullet is desugared into one bullet per item BEFORE anything flips
    # (issue #131). After this the flip below can only move `num`.
    lines = _split_multi_item_bullets(lines, num, status)
    # Flip the icon of every bullet whose trailing marker names this item —
    # the same ownership rule `_parse_item_status` reads by (issue #99), so a
    # bullet that merely mentions the item in prose is never flipped.
    for start, last in _deliverable_bullet_spans(lines):
        if num not in _bullet_marker_item_numbers(lines[last]):
            continue
        current = ICON_TO_STATUS[_BULLET_RE.match(lines[start]).group("icon")]
        if current and RANK[status] > RANK[current]:
            lines[start] = _replace_first_icon(lines[start], status)

    # Recompute rollups for every stage (never downgrading).
    stage_status: Dict[str, str] = {}
    for start, end, stage_num in stage_sections(lines):
        derived = rollup_status(stage_deliverable_statuses(lines, start, end))
        if derived is None:
            continue
        stage_status[stage_num] = derived
        _set_stage_header(lines, start, derived)
        _set_summary_row(lines, stage_num, derived)
    _apply_objective_rollup(lines, stage_status)

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# Item & queue file naming — the filename half of the branch helpers
# --------------------------------------------------------------------------- #
#: Item numbers and queue numbers share one namespace with no syntactic marker
#: between them. `_branch_item_number`/`_is_queue_branch` centralise that hazard
#: for BRANCH names (and their docstrings record what it cost to learn); these
#: four do the same for FILE names, which were previously re-derived as raw
#: globs and f-strings at thirteen call sites. Nothing here fixes a live bug —
#: every one of those sites was correct. The point is that the convention is now
#: written down once, so the 1.13.0 class of misread has one place to reappear
#: and one place to be tested, and a change to the convention is a change here.


#: The literal tokens every queue name is built from — the file stem, both
#: branch shapes, and the regexes that read them back. Written once so that a
#: change to the convention is a change *here* and everything moves with it;
#: restating "queue-" in a constructor and again in a recogniser is exactly the
#: drift 1.15.0 removed for filenames and this block removes for branches.
_QUEUE_TOKEN = "queue-"
_SPECS_TOKEN = "specs-"


def queue_name(number: int) -> str:
    """``queue-NNN`` — the stem a queue file and its status prose both use."""
    return f"{_QUEUE_TOKEN}{number:03d}"


def queue_number(path: Path) -> Optional[int]:
    """Queue number named by *path*, or None when it names no queue.

    Anchored at the start of the stem, for the same reason the branch helpers
    are: an unanchored digit search reads ``specs-queue-015.md`` or a consumer's
    ``notes-on-queue-016.md`` as a queue file. Tolerates a trailing slug
    (``queue-016-stage-27.md``) so the deferred naming harmonisation does not
    have to touch the parser, and unpadded digits on read.
    """
    m = re.match(re.escape(_QUEUE_TOKEN) + r"0*(\d+)(?:-|$)", path.stem)
    return int(m.group(1)) if m else None


def iter_queue_paths(qdir: Path) -> List[Path]:
    """Every queue file under *qdir*, in queue-number order ([] if no dir).

    Ordered by the parsed number rather than lexicographically, so the order
    stays the number's even once a name carries a slug after it.
    """
    if not qdir.is_dir():
        return []
    numbered = [(n, p.name, p) for p, n in
                ((p, queue_number(p)) for p in qdir.glob(f"{_QUEUE_TOKEN}*.md"))
                if n is not None]
    return [p for _, _, p in sorted(numbered)]


def queue_path(qdir: Path, number: int) -> Optional[Path]:
    """The queue file for *number*, or None when it does not exist.

    **Resolves by glob, never by construction.** Constructing
    ``qdir / f"queue-{n:03d}.md"`` hardcodes the assumption that the number is
    the whole name; resolving means a slugged queue file is found by the same
    call, and a caller that wants a name for an error message asks
    `queue_name` for one instead of half-building a path it may not have.
    """
    matches = [p for p in iter_queue_paths(qdir) if queue_number(p) == number]
    return matches[0] if matches else None


def item_spec_paths(idir: Path, number: int) -> List[Path]:
    """Spec files for item *number* under *idir* — ``items/NNN-*.md``, sorted.

    Returns a list because the convention permits only one and the filesystem
    does not; every caller takes ``[0]`` and the extras are a consumer's
    problem, not something to raise over here.
    """
    if not idir.is_dir():
        return []
    return sorted(idir.glob(f"{number:03d}-*.md"))


# --------------------------------------------------------------------------- #
# queue.md helpers
# --------------------------------------------------------------------------- #
_QUEUE_STATUS_RE = re.compile(r"^>\s*\*\*Status:\*\*\s*(.*)$")
_QUEUE_ITEM_RE = re.compile(r"^###\s+Item\s+0*(\d+)\b", re.MULTILINE)


def queue_status(text: str) -> Optional[str]:
    for line in text.splitlines():
        m = _QUEUE_STATUS_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def is_live_queue(text: str) -> bool:
    status = queue_status(text) or ""
    return status.lower().startswith("live")


def queue_item_numbers(text: str) -> List[int]:
    return [int(m.group(1)) for m in _QUEUE_ITEM_RE.finditer(text)]


def queue_is_open(text: str, item_status: Dict[int, str]) -> bool:
    """Derived queue state: open iff any item is 📋/🚧/🔍 per progress.md.

    🔍 counts as open: an item whose PR is still awaiting review is not work the
    queue is finished with, and marking the queue completed over it would strand
    the review.

    Queue state is DERIVED, never declared — a ``> **Status:**`` line in a
    queue file is decorative (kept for human readers), and the "live" queue is
    simply the lowest-numbered open one. An item progress.md doesn't know yet
    counts as planned, so a freshly wired queue is open.
    """
    return any(item_status.get(n, "planned") in ("planned", "in-progress", "in-review")
               for n in queue_item_numbers(text))


def _progress_item_status(repo_root: Path, config) -> Dict[int, str]:
    path = docs_dir(repo_root, config) / "progress.md"
    if not path.is_file():
        return {}
    _, _, item_status = _parse_item_status(path.read_text(encoding=_ENCODING).splitlines())
    return item_status


def tidy_queue_text(text: str, superseded_by: int, date: str) -> str:
    """Rewrite a queue's Status line to 'Completed — superseded by queue-NNN'."""
    new_status = (f"> **Status:** ✅ Completed — superseded by "
                  f"{queue_name(superseded_by)} ({date}).")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _QUEUE_STATUS_RE.match(line):
            lines[i] = new_status
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    # No status line: insert after the H1.
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 1, new_status)
            break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
#: An AIDE slot is a bare ``{{name}}``. The negative lookbehind exempts a `$`
#: immediately before the braces — GitHub Actions expression syntax, which is
#: foreign syntax a living document may legitimately quote when it documents a
#: workflow. Without it, an item spec explaining what a CI step runs, or an
#: insight recording a workflow's arguments, turns `aide check` red on prose
#: that is correct as written, and the only remedy is to stop naming the real
#: syntax — making the documentation worse exactly where accuracy matters.
#:
#: Suppressing matches inside backtick code spans would be the wrong fix: the
#: item template's own `Suggested branch` line carries a genuine slot inside a
#: code span (``aide/{{nnn}}-descriptive-name``), so that rule would make a
#: real unfilled slot invisible. AIDE slots are never `$`-prefixed, so keying
#: on the `$` is precise in both directions.
_TEMPLATE_SLOT_RE = re.compile(r"(?<!\$)\{\{[^}]*\}\}")


def template_residue_errors(ddir: Path) -> List[str]:
    """Flag unfilled ``{{slot}}`` template markers left in generated documents.

    Templates use ``{{slot-name}}`` for values an author must fill in (see
    ``.aide/templates/``); a real ``docs/aide/`` document should never contain
    one. Scanning for the literal ``{{`` is deterministic and cheap — the
    format contract's answer to "did someone forget to fill in the template".
    """
    errors: List[str] = []
    if not ddir.is_dir():
        return errors
    for path in sorted(ddir.rglob("*.md")):
        text = path.read_text(encoding=_ENCODING)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _TEMPLATE_SLOT_RE.finditer(line):
                errors.append(
                    f"{path.relative_to(ddir).as_posix()}:{lineno}: "
                    f"unfilled template slot {m.group(0)}"
                )
    return errors


_INSIGHT_TYPES = ("knowledge", "defect", "gap", "automation", "framework")
#: What may stand between ``*(`` and the date: anything but a close-paren or a
#: line break, or nothing at all.
#:
#: Deliberately a slug and not a grammar. Only the **date** is load-bearing —
#: ``archive`` cuts on it and ``list`` prints it; nothing routes on the item
#: number — while the frame around the provenance already pins the checkbox, a
#: known type, the dash, a non-empty claim and an ISO date. A provenance that
#: fails an enumerated shape inside that frame names no defect anyone can act
#: on.
#:
#: Enumerating the accepted forms means predicting what an author will write,
#: and the cost of predicting wrong is not the usual one: conventions.md §1
#: makes the captured line immutable, so a rejected provenance is a warning
#: that can never be cleared, on an entry ``archive`` then declines to move
#: (see ``archive_insight_text``). Until 1.21.0 the shape was ``item NNN``
#: alone, which rejected two provenances the loop produces routinely —
#: ``queue-NNN`` for planning done before any item exists, and
#: ``items NNN-NNN`` for a finding that genuinely spans several. Both were
#: unfixable in place, since collapsing a range to one item is a rewording
#: *and* destroys the provenance the marker exists to record.
#:
#: Canonical forms are still documented (conventions.md §1, and the template's
#: header) so captures converge — guidance, which the reader can follow, rather
#: than enforcement, which the immutability rule makes permanent.
#:
#: It must still end in a non-blank character, so a stray comma — ``*(   ,
#: 2026-01-01)*`` — is a shape warning rather than a silently accepted
#: provenance that says nothing. Free-form is not the same as empty.
_INSIGHT_SOURCE = r"[^)\n]*[^\s)\n]"
#: What may stand **after** the date, in the same marker: the conditions the
#: observation was made under, conventionally ``engine X.Y.Z`` — one read of
#: ``.aide/VERSION`` at capture time (conventions.md §1).
#:
#: The date cannot proxy for it: a project runs an engine for as long as it
#: likes after a release, so two entries captured the same week may sit either
#: side of a restructure. It matters most on a ``framework`` entry, which is
#: triaged in another repo, months later, by someone with no other way to know.
#:
#: Free-form for the same reason the provenance is, and the reason is sharper
#: here: this component arrived after entries already existed, so a grammar
#: (``engine`` plus a SemVer triple, say) would reject a consumer's own honest
#: spelling permanently — the claim line is immutable, and the warning could
#: never be cleared. Conventional, not grammatical.
#:
#: Free-form everywhere except one character: ``)`` closes the marker, so a note
#: containing one — ``engine 1.2.3 (rc1)`` — does not parse, drawing a permanent
#: shape warning and losing the date that ``archive`` and ``tick`` read. Write
#: the note without parentheses.
_INSIGHT_NOTE = r"[^)\n]*[^\s)\n]"
#: A provenance naming exactly one item — the only form that yields an item
#: *number*. A range, a queue, or anything else leaves ``item`` ``None``, as a
#: bare date always has.
_INSIGHT_ONE_ITEM_RE = re.compile(r"^[Ii]tems? (\d+)$")
# "- [ ] <type> — <one line> *(item NNN, YYYY-MM-DD, engine X.Y.Z)*"; the
# provenance and the trailing note are both free-form and optional, and ticked
# entries append " → <where it landed>".
_INSIGHT_RE = re.compile(
    r"^- \[[ xX]\] (?:" + "|".join(_INSIGHT_TYPES) + r") [—–-] .+"
    r"\*\((?:" + _INSIGHT_SOURCE + r", )?\d{4}-\d{2}-\d{2}"
    r"(?:, " + _INSIGHT_NOTE + r")?\)\*"
)


def insight_warnings(ddir: Path) -> List[str]:
    """Shape-check ``insights.md`` (the compound-engineering inbox), if present.

    Non-blocking: capture must stay cheap, so a malformed entry is a warning,
    never an error. Every ``- `` bullet in the file is expected to be an entry.

    **The live file only.** ``aide insights archive`` moves closed entries into
    ``insights/archive-YYYY-QN.md``, and those are deliberately not re-checked
    here: an archived claim is frozen, so a warning on one names a defect no
    one may fix — the immutability rule forbids rewording the line. (Unfilled
    ``{{slot}}`` markers *are* still caught in archives, because
    ``template_residue_errors`` walks the whole tree; that one is a genuine
    error wherever it appears.)
    """
    path = ddir / "insights.md"
    if not path.is_file():
        return []
    out: List[str] = []
    for lineno, line in enumerate(path.read_text(encoding=_ENCODING).splitlines(), start=1):
        if not line.startswith("- "):
            continue
        if not _INSIGHT_RE.match(line):
            out.append(
                f"insights.md:{lineno}: entry does not match "
                f"'- [ ] <{'|'.join(_INSIGHT_TYPES)}> — <one line> "
                f"*(<where it came from>, YYYY-MM-DD, engine X.Y.Z)*' — the "
                f"provenance and the trailing engine version are free-form "
                f"and may be omitted; the ISO date may not"
            )
    return out


#: An entry's full shape, parsed rather than merely validated: the claim, its
#: provenance, and the optional " → <where it landed>" pointer a tick appends.
#: ``text`` is non-greedy up to the provenance so a claim may itself contain
#: parentheses; ``tail`` is whatever follows it, which is the pointer or "".
#: The pointer separator, written by `tick` and by hand before it existed.
_INSIGHT_POINTER = " → "
#: ``source`` is the provenance verbatim (``None`` for a bare date), because a
#: listing that re-derives it from an item number can print nothing else back.
_INSIGHT_ENTRY_HEAD = (
    r"^- \[(?P<mark>[ xX])\] (?P<type>" + "|".join(_INSIGHT_TYPES) + r") [—–-] "
    r"(?P<text>.+?)\*\((?:(?P<source>" + _INSIGHT_SOURCE + r"), )?"
    r"(?P<date>\d{4}-\d{2}-\d{2})(?:, (?P<note>" + _INSIGHT_NOTE + r"))?\)\*"
)
#: Which marker is the provenance, when a line carries more than one.
#:
#: ``text`` is non-greedy, so it stops at the *first* ``*(…, date)*`` — and a
#: free-form provenance means an aside inside the claim can wear that shape:
#: ``… default is *(prod, 2020-01-01)* not *(item 099, 2026-07-26)*`` would take
#: the aside's date and file the entry in the wrong archive quarter, silently,
#: since the line still parses. Greedy is not the answer either — it takes the
#: *last* marker, which a pointer may equally carry (``→ see *(note, …)*``).
#:
#: So neither position decides it: the provenance is the marker that leaves a
#: **well-formed tail** — nothing, or the ``→`` pointer `tick` writes. That is
#: the strict pattern, and it resolves both cases above. A tail matching
#: neither is a hand-written entry predating `tick` (``*(…)* — landed in X``);
#: the loose pattern accepts it exactly as before, so widening the provenance
#: costs no entry its parse.
_INSIGHT_FULL_RE = re.compile(_INSIGHT_ENTRY_HEAD + r"(?P<tail>\s*(?:→.*)?)$")
_INSIGHT_FULL_LOOSE_RE = re.compile(_INSIGHT_ENTRY_HEAD + r"(?P<tail>.*)$")
#: A status-trail line: indented under its entry, newest last (conventions.md
#: §1). Indentation is what distinguishes it from the next entry, so this must
#: require leading whitespace where the entry pattern forbids it.
_INSIGHT_TRAIL_RE = re.compile(r"^\s+[-*]\s")
#: An ISO date, validated rather than trusted: `archive --before` compares it
#: lexicographically against every entry's date, which is only equivalent to
#: comparing dates while both sides are known to be YYYY-MM-DD.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InsightEntry(NamedTuple):
    """One inbox entry: the parsed claim plus where it sits in the file.

    ``ordinal`` is 1-based position in the live file and is the identity every
    verb here takes, because an entry has no number of its own. That is sound
    only because the file is append-only by contract — a claim is "never
    reworded, reordered or deleted" — so an entry's position is stable for as
    long as it lives in the file. ``archive`` is the one thing that moves
    entries out, and it therefore renumbers what remains; it says so when it
    runs, and ``tick`` refuses to invent a pointer on a number it cannot
    resolve.

    A malformed entry (one ``aide check`` warns about) still gets an ordinal.
    Skipping it would make ``insights list`` number entries differently from
    the file itself, so the one number a reader can act on would be wrong for
    every entry after the first typo.
    """

    ordinal: int
    lineno: int                 # 1-based, of the entry line itself
    raw: str                    # the entry line, verbatim
    ticked: bool
    type: Optional[str]         # None when the line does not parse
    text: str                   # the claim, without provenance or pointer
    date: Optional[str]
    source: Optional[str]       # the provenance verbatim; None for a bare date
    note: Optional[str]         # what follows the date, verbatim — by
                                # convention "engine X.Y.Z"; None when absent
    item: Optional[int]         # only when `source` names exactly one item
    pointer: Optional[str]      # what follows " → ", when ticked in place
    trail: List[str]            # raw status-trail lines, in file order
    end_lineno: int             # 1-based, of the entry's last trail line


def parse_insights(text: str) -> List[InsightEntry]:
    """Parse ``insights.md`` into entries, malformed ones included.

    Pure: it takes the file's text, never a path, so the shape rules are
    testable without a filesystem (the module convention — see
    ``.aide/scripts/tests``).
    """
    lines = text.splitlines()
    entries: List[InsightEntry] = []
    for lineno, line in enumerate(lines, start=1):
        if not line.startswith("- "):
            if entries and _INSIGHT_TRAIL_RE.match(line):
                # A trail line belongs to the entry above it; NamedTuple is
                # immutable, so grow the list it holds rather than rebuilding.
                entries[-1].trail.append(line)
                entries[-1] = entries[-1]._replace(end_lineno=lineno)
            continue
        m = _INSIGHT_FULL_RE.match(line) or _INSIGHT_FULL_LOOSE_RE.match(line)
        if m is None:
            entries.append(InsightEntry(
                ordinal=len(entries) + 1, lineno=lineno, raw=line,
                ticked=line.startswith("- [x]") or line.startswith("- [X]"),
                type=None, text=line[2:].strip(), date=None, source=None,
                note=None, item=None, pointer=None, trail=[],
                end_lineno=lineno))
            continue
        tail = m.group("tail")
        pointer = (tail.split(_INSIGHT_POINTER, 1)[1].strip()
                   if _INSIGHT_POINTER in tail else None)
        source = m.group("source")
        one_item = _INSIGHT_ONE_ITEM_RE.match(source) if source else None
        entries.append(InsightEntry(
            ordinal=len(entries) + 1, lineno=lineno, raw=line,
            ticked=m.group("mark") in ("x", "X"),
            type=m.group("type"), text=m.group("text").strip(),
            date=m.group("date"), source=source, note=m.group("note"),
            item=int(one_item.group(1)) if one_item else None,
            pointer=pointer, trail=[], end_lineno=lineno))
    return entries


def _find_entry(entries: List[InsightEntry], ordinal: int) -> InsightEntry:
    for e in entries:
        if e.ordinal == ordinal:
            return e
    raise ValueError(
        f"no entry {ordinal} — the file holds {len(entries)} "
        f"entr{'y' if len(entries) == 1 else 'ies'}; run `insights list` for "
        f"current numbers (an archive renumbers what remains)")


def tick_insight_text(text: str, ordinal: int, pointer: str,
                      date: str) -> Tuple[str, str]:
    """Tick entry *ordinal*, or append a dated trail line if already ticked.

    The two halves of conventions.md §1's lifecycle, chosen by the entry's own
    state rather than by a flag: the **first** routing flips the checkbox and
    records where the claim landed on the entry line; **everything after** it —
    a re-route, a resolution, a premise that decayed — is bookkeeping and goes
    in the appendable status trail underneath.

    The captured claim is never touched by either path. Returns
    ``(new_text, message)``; raises ``ValueError`` if the ordinal does not
    resolve or the entry is too malformed to edit safely.
    """
    if "\n" in pointer or "\r" in pointer:
        raise ValueError(
            "the pointer may not contain a line break — it is written into a "
            "single entry line, so a break would split one claim into two and "
            "renumber everything below it")
    entries = parse_insights(text)
    entry = _find_entry(entries, ordinal)
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")

    if entry.ticked:
        # end_lineno is 1-based, so as a 0-based list index it is the slot
        # just past the entry's last line — where the next trail line goes.
        insert_at = entry.end_lineno
        indent = "  "
        if entry.trail:
            indent = entry.trail[-1][: len(entry.trail[-1]) - len(entry.trail[-1].lstrip())]
        lines.insert(insert_at, f"{indent}- **{date}** {_INSIGHT_POINTER.strip()} {pointer}")
        message = f"entry {ordinal}: already ticked — appended a {date} trail line"
    else:
        if entry.type is None:
            raise ValueError(
                f"entry {ordinal} does not parse as an inbox entry, so there "
                f"is no checkbox to tick safely: {entry.raw!r}. Fix the line's "
                f"shape first (`aide check` names the rule)")
        line = entry.raw.replace("- [ ]", "- [x]", 1)
        if entry.pointer is None:
            line = line + _INSIGHT_POINTER + pointer
            message = f"entry {ordinal}: ticked → {pointer}"
        else:
            # A pointer written by hand before the tick: keep it, and record
            # this routing where a second one belongs.
            lines[entry.lineno - 1] = line
            # 1-based end_lineno as a 0-based index = just past the entry.
            lines.insert(entry.end_lineno,
                         f"  - **{date}** {_INSIGHT_POINTER.strip()} {pointer}")
            return ("\n".join(lines) + ("\n" if trailing_newline else ""),
                    f"entry {ordinal}: ticked; existing pointer kept, "
                    f"added a {date} trail line")
        lines[entry.lineno - 1] = line

    return ("\n".join(lines) + ("\n" if trailing_newline else "")), message


def insight_quarter(date: str) -> str:
    """``"2026-08-24"`` → ``"2026-Q3"`` — the archive file an entry belongs to."""
    year, month = int(date[:4]), int(date[5:7])
    return f"{year}-Q{(month - 1) // 3 + 1}"


def archive_insight_text(
    text: str, before: str,
) -> Tuple[str, Dict[str, List[str]], List[InsightEntry]]:
    """Split closed entries dated before *before* out of the live file.

    Returns ``(remaining_text, {quarter: [lines]}, undatable)``, where
    ``undatable`` holds the **closed entries this pass could not date** and so
    could not consider. An entry too malformed to yield a date is excluded from
    every ``--before`` cut however old and however closed it is, and reporting
    it here is what keeps that from being silent: the same pass that declines
    to move it says which lines they were, so the operator can fix a shape
    instead of wondering why the live file will not shrink. It is returned
    rather than logged because this helper is pure — the caller prints.

    **Only ticked entries move**: an open entry is the live working set whatever its date, and
    archiving one would hide exactly the backlog this verb exists to surface.
    An entry travels with its whole status trail, so the archive stays readable
    on its own.

    Pure, and it never rewrites a claim: each line's *text* is carried across
    unchanged, which is what keeps the immutability rule true through the move.
    Line endings are not carried — like every writer in this module, it rebuilds
    the text with ``\n`` — so the promise is the claim, not the bytes around it.
    """
    lines = text.splitlines()
    entries = parse_insights(text)
    moving = {e.ordinal for e in entries
              if e.ticked and e.date is not None and e.date < before}
    # Closed, so it was a candidate; undated, so no cut can ever reach it.
    undatable = [e for e in entries if e.ticked and e.date is None]
    moved: Dict[str, List[str]] = {}
    drop: set = set()
    for e in entries:
        if e.ordinal not in moving:
            continue
        block = lines[e.lineno - 1:e.end_lineno]
        moved.setdefault(insight_quarter(e.date), []).extend(block)
        drop.update(range(e.lineno - 1, e.end_lineno))
    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    return _collapse_blank_runs(kept, text.endswith("\n")), moved, undatable


def _collapse_blank_runs(lines: List[str], trailing_newline: bool) -> str:
    """Join *lines*, leaving at most one blank line where entries were removed.

    Lifting entries out of a blank-separated list otherwise leaves the gaps
    behind, and a file that grows whitespace every time it is tidied is not
    tidied.
    """
    out: List[str] = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if trailing_newline else "")


def absolute_path_test_warnings(repo_root: Path,
                                config: Dict[str, Dict[str, object]]) -> List[str]:
    """Warn on a test file containing the repository's own absolute path.

    The one portability rule of conventions.md §6 a script can decide, and the
    one whose recorded instance was invisible to every other gate for weeks: a
    test pinned the authoring sandbox's own filesystem path instead of
    resolving relative to the test file. Because that path *is* where the
    project sits on that machine, it passed the builder's run, both validator
    rounds, and even a fresh clone into a different directory — an absolute
    path ignores where the process runs from. On every CI runner the glob
    matched nothing, the digest collapsed to SHA-256 of empty input, and all
    four legs failed.

    Matching the repo root literally keeps this exact: a test that hardcodes
    the path of the repository it lives in is wrong on any other machine, with
    no judgement call and no false positive to argue about.
    """
    tests_dir = repo_root / str(config["project"].get("tests_dir", "tests"))
    if not tests_dir.is_dir():
        return []
    # Three spellings, because the offending literal is whatever the authoring
    # platform wrote and this check must fire wherever it runs. On POSIX all
    # three collapse to one string; on Windows they are genuinely different:
    #   as_posix()  C:/path/to/repo    — a forward-slash literal
    #   str()       C:\path\to\repo    — a raw string, r"C:\path\to\repo"
    #   escaped     C:\\path\\to\\repo — an ordinary literal, the COMMON form
    # Omitting the third would make this portability lint miss the most likely
    # Windows spelling of the very defect it exists to catch.
    root = repo_root.resolve()
    needles = {root.as_posix(), str(root), str(root).replace("\\", "\\\\")}
    out: List[str] = []
    for path in sorted(tests_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding=_ENCODING)
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(n in line for n in needles):
                rel = _rel_display(path, repo_root)
                out.append(
                    f"{rel}:{lineno}: contains this repository's absolute path — "
                    f"it passes here and matches nothing on any other checkout; "
                    f"resolve from the test file instead "
                    f"(Path(__file__).resolve().parents[N]). See conventions.md §6")
                break   # one warning per file is enough to act on
    return out


def _is_gate_table_furniture(cells: List[str]) -> bool:
    """True for the gates table's header or separator row — never for data.

    The separator test requires a NON-EMPTY cell. `set("") <= set("-: ")` is
    true, so an empty first cell used to read as a separator: a malformed row
    like `| | 028 | ⏳ Awaiting | a | pipe |` was skipped *silently*, which is
    precisely the vanishing-gate failure the warning below exists to catch.
    """
    if not cells:
        return True
    first = cells[0]
    return first.lower() == "gate" or bool(first.strip()) and set(first) <= set("-: ")


def _malformed_gate_row_warnings(lines: List[str]) -> List[str]:
    """Rows inside the gates table the parser had to skip.

    A gate is only useful if it is read, so a row with the wrong column count
    must not vanish in silence — that turns "a person must decide this" into
    "nothing is blocking", which is the most dangerous way this feature can
    fail. The CLI refuses to write a `|` into a cell; this catches the rest
    (a hand edit, a paste).
    """
    out: List[str] = []
    in_section = False
    for i, line in enumerate(lines):
        if _GATES_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _ANY_HEADER_RE.match(line):
            break
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_row(line)
        if _is_gate_table_furniture(cells) or len(cells) == 4:
            continue
        out.append(
            f"progress.md:{i + 1}: human-gate row has {len(cells)} columns, not 4 — "
            f"it is being SKIPPED, so whatever it was meant to block is not "
            f"blocked. A '|' inside a cell is the usual cause.")
    return out


def _reach_with_breadth(lines: List[str], g: HumanGate) -> str:
    """*g*'s reach with the held items resolved and counted.

    A ``stage N`` reach reads plausibly right while holding items its author
    never meant to hold — the observed case gated the very deliberation that
    was to produce the gate's evidence. ``aide claim`` already names what it
    holds, but that surfaces only when a runner stalls; the check computes the
    same breadth (``stage_item_numbers``) and used to throw it away, so the
    contradiction was invisible at authoring time. Only the stage form needs
    resolving: an item-list reach already names its items, and ``all`` is its
    own answer.

    The count covers the items the gate still sits in front of: a ✅ item has
    merged and a ❌ one is out, so "holding" either would overstate the reach
    against the very enforcement this message mirrors. (``claim``'s stall
    report narrows further, to the claimable subset of one queue — that is
    the runtime view; this is the authoring-time view of the same fact, and a
    stage whose every item merged falls back to the bare reach.)
    """
    if g.stage is None:
        return g.reach
    _, _, item_status = _parse_item_status(lines)
    items = [i for i in stage_item_numbers(lines, g.stage)
             if item_status.get(i, "planned") not in ("complete", "excluded")]
    if not items:
        return g.reach
    return (f"stage {g.stage} — holding {len(items)} item(s): "
            + ", ".join(f"{i:03d}" for i in items))


def gate_warnings(lines: List[str]) -> List[str]:
    """One warning per unresolved human gate, plus one per unreadable row.

    A warning, never an error: an outstanding gate is a normal state — work is
    waiting on a person, which is what it is for. The point is that the state
    is *visible* rather than buried in an item spec's prose.
    """
    out: List[str] = []
    out.extend(_malformed_gate_row_warnings(lines))
    for n, g in enumerate(human_gates(lines), start=1):
        if g.kind == "approved":
            continue
        if g.kind is None:
            out.append(
                f"progress.md:{g.lineno}: human gate {n} ({g.text}) has an "
                f"unrecognised status — use ⏳ Awaiting, ✅ Approved or ❌ Declined; "
                f"until it reads one of those the gate counts as unresolved")
            continue
        if g.kind == "declined":
            out.append(
                f"progress.md:{g.lineno}: human gate {n} ({g.text}) was DECLINED "
                f"and still blocks {_reach_with_breadth(lines, g)} — a refusal does not release the "
                f"work it guards; drop those items or change what the gate asks")
            continue
        if g.stage is not None and not stage_item_numbers(lines, g.stage):
            # An empty reach has two causes and only one is a mistake.
            if stage_section(lines, g.stage) is None:
                # No such section: a typo, invisible otherwise — the gate looks
                # like it guards a stage while holding nothing at all, ever.
                reach = (f"stage {g.stage} — which has no deliverable "
                         f"referencing any item, so this gate holds NOTHING; "
                         f"check the stage number")
            else:
                # The section is there and simply has nothing queued for it
                # yet. Raising a gate before the work exists is the cheapest
                # time to raise one, and `stage N` reach re-resolves through
                # progress.md on every read — so this gate is armed and will
                # hold that stage's items as they appear. Calling the feature's
                # own happy path a typo trains the reader to ignore the check.
                reach = (f"stage {g.stage} — which has no items queued yet, so "
                         f"it holds nothing today and will block that stage's "
                         f"items as they are created")
        elif g.blocks or g.stage or g.blocks_all:
            reach = _reach_with_breadth(lines, g)
        else:
            reach = ("nothing named — the Blocks cell names no item, no "
                     "'stage N', and is not 'all', so this gate holds nothing")
        out.append(f"progress.md:{g.lineno}: human gate {n} ({g.text}) is "
                   f"awaiting a decision — blocks {reach}")
    return out


#: A deliverable bullet must be FLAT (conventions.md §1). `_BULLET_RE` allows
#: leading whitespace, so a nested bullet is read as a **full deliverable** —
#: not ignored. That is the hazard: nesting implies subordination to a reader
#: while the rollup counts it as a peer, so a `📋` child silently drags its ✅
#: parent's stage to 🚧. Verified: ['complete', 'planned'] -> in-progress.
_NESTED_DELIVERABLE_RE = re.compile(r"^\s+[-*]\s*(?P<icon>" + _ICON_ALT + r")")

#: Documents whose template carries a header blockquote. Not every file under
#: docs_dir: a generated artifact or a project note is not a living document,
#: and insights.md's template deliberately opens with a comment instead.
_BLOCKQUOTE_DOCS = ("vision.md", "roadmap.md", "progress.md")

#: A status FIELD in an item header: `**Status:** x` or `**Status**: x`. The
#: colon is required, so bold emphasis on the word in prose is not a match.
_ITEM_STATUS_FIELD_RE = re.compile(
    r"\*\*\s*(?P<name>Status|Completed)\s*(?::\s*\*\*|\*\*\s*:)")


#: Calls that spawn a process. Matched through the AST, never by line text: the
#: one occurrence in the consumer measured against was a DOCSTRING explaining
#: why the author had removed a subprocess — a line-based lint flags the file
#: documenting the correct practice.
_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})


def _rel_display(path: Path, repo_root: Path) -> str:
    """*path* relative to the repo for a message, falling back to absolute.

    `tests_dir` may be configured absolute or resolve outside the repo via a
    symlink, and `relative_to` raises then. Shared by every test-hygiene lint:
    fixing this once in `absolute_path_test_warnings` and then hand-writing the
    same call in two new ones is exactly how it came back.
    """
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _test_files(repo_root: Path, config: Dict[str, Dict[str, object]]) -> List[Path]:
    tests_dir = repo_root / str(config["project"].get("tests_dir", "tests"))
    if not tests_dir.is_dir():
        return []
    return [p for p in sorted(tests_dir.rglob("*.py"))
            if "__pycache__" not in p.parts]


def separator_dependent_test_warnings(repo_root: Path,
                                      config: Dict[str, Dict[str, object]]) -> List[str]:
    """Tests stringifying a relative `Path` into a value that gets compared.

    conventions.md §6: any `Path` entering a hash, comparison or match must be
    `.as_posix()`. Narrowed to `.relative_to(`, the shape all four recorded
    CI-only failures took, reached two ways — an explicit `str(...)` and an
    f-string, which calls `str()` for you.

    Matched through the AST, because a regex cannot tell an f-string's `{...}`
    from a dict or set literal: `{p.relative_to(root): 1}` never stringifies the
    Path and must not be flagged. A lint that cries wolf stops being read.
    """
    out: List[str] = []
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        def _ends_in_relative_to(node) -> bool:
            """True when the OUTERMOST call of *node* is `.relative_to(...)`.

            Deliberately the outermost, not anywhere in the subtree: searching
            the subtree flags `str(p.relative_to(root).as_posix())`, which is
            already separator-stable and is exactly what the rule asks for.
            Flagging compliant code is how a lint stops being read, so this
            errs narrow — it reports the recorded shape and stays quiet on
            anything already normalised.
            """
            return (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "relative_to")

        for node in ast.walk(tree):
            hit = False
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "str" and len(node.args) == 1):
                hit = _ends_in_relative_to(node.args[0])
            elif isinstance(node, ast.JoinedStr):
                hit = any(_ends_in_relative_to(v.value) for v in node.values
                          if isinstance(v, ast.FormattedValue))
            if hit:
                out.append(
                    f"{_rel_display(path, repo_root)}:{node.lineno}: a relative "
                    f"Path rendered with str() carries the OS separator, so this "
                    f"value differs on Windows — use .as_posix() "
                    f"(conventions.md §6)")
                break
    return out


def cli_subprocess_test_warnings(repo_root: Path,
                                 config: Dict[str, Dict[str, object]]) -> List[str]:
    """Tests shelling out to `aide.py` instead of calling its function.

    conventions.md §6: prefer calling the function over shelling out to the
    command that calls it. The logic is importable and returns structured data;
    the subprocess adds stdout encoding, platform quirks, and a re-parse of what
    was structured a moment earlier. The recorded instance returned
    ``stdout is None`` on a Windows runner — and had it returned ``""`` the test
    would have passed while checking nothing.

    **No exemption for the self-referential case**, asked for and declined
    (issue #123). A test whose whole job is to replay `aide check`'s literal
    stdout trips this rule, which reads like the verb flagging itself. It is
    not: `cmd_check` calls `run_checks`, that function returns
    ``(errors, warnings)`` as structured data, and asserting on it in-process
    is both the fix and the better test — which is what the reporting consumer
    did. Exempting the shape would license the worse test in the one place the
    argument for it sounds strongest.

    What the report actually found is a *measurement* defect, and it belongs to
    the spec, not to this lint: a module that shells out to the CLI raises the
    warning count by one the moment it is committed, so any baseline count
    recorded before it existed is falsified by the act of adding it. Measured:
    a spec recorded 3, the base commit already carrying the module reported 4,
    and the 4th was the module. §6 now says never to pin a count that way.
    """
    out: List[str] = []
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _SUBPROCESS_FUNCS:
                continue
            if any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                   and "aide.py" in c.value for c in ast.walk(node)):
                rel = _rel_display(path, repo_root)
                out.append(
                    f"{rel}:{node.lineno}: shells out to aide.py — call the "
                    f"function instead (e.g. run_checks); a subprocess adds a "
                    f"stdout/encoding surface that has failed on Windows only, "
                    f"and can pass while checking nothing (conventions.md §6)")
                break
    return out


#: Branch names a hardcoded diff range is written against. The configured
#: `main_branch` is the honest one; `main` and `master` ride along because this
#: shape is copied between projects — a consumer whose base is `develop` and
#: whose test says `main...HEAD` has written the same wrong assertion, and the
#: lint that only knew its own config would stay silent on it.
_CONVENTIONAL_BASES = ("main", "master")


def _scope_range_re(config: Dict[str, Dict[str, object]]) -> "re.Pattern":
    names = {str(config["git"].get("main_branch", "main")), *_CONVENTIONAL_BASES}
    alt = "|".join(re.escape(n) for n in sorted(names))
    return re.compile(rf"\b(?:origin/)?(?:{alt})\.{{2,3}}HEAD\b"
                      rf"|\bHEAD\.{{2,3}}(?:origin/)?(?:{alt})\b")


def scope_claim_test_warnings(repo_root: Path,
                              config: Dict[str, Dict[str, object]]) -> List[str]:
    """Diff-time scope claims written as suite assertions.

    §1 → authorised-paths says a *diff-time scope claim* — "item N did not touch
    X" — belongs under **Asserts against** and is retired when its item merges,
    and `cmd_scope` exists precisely so the claim is not "enshrined as a suite
    assertion that outlives its truth". Both statements were already written
    down, and reached neither the spec-author writing the criterion nor the
    test-writer implementing it: two independent items in one consumer wrote the
    same `git diff main...HEAD` guard (issue #132), which is the signature of a
    missing check rather than a careless author.

    The shape fails in the direction that wastes the most time. Under a stacked
    queue the item's base is the **queue branch**, so `main` is stale by the
    whole queue and every sibling item's legitimate change is reported as this
    item's scope violation. The obvious repair is wrong too: deriving the base
    from `aide scope` makes the assertion pass only while the suite runs on the
    item's own claim branch, and `aide merge` re-runs that suite from the merge
    target — so it fails by construction inside the loop's own post-merge run.
    Skip-guarding is not an escape either: once the claim branch is deleted the
    test is skipped forever, which §6 ("tests that can actually fail") forbids.

    **Two literal shapes, deliberately, and no attempt at the general one.** A
    hardcoded `<base>...HEAD` range, and a shell-out to `aide scope`. A test
    that diffs the branch against a base it computes — `git merge-base HEAD
    origin/main`, then `diff` — is NOT reported, and this framework's own
    `tests/test_repo_versioning.py` is why: it is that shape, it is legitimate,
    and it is a claim about the branch rather than about an item's scope. No
    lint can tell those apart from the source, so this one decides only what is
    literal, and §6's rule holds where it cannot look. An interpolated range
    (`f"{base}...HEAD"`) is missed for the same reason.

    The `aide scope` half also trips `cli_subprocess_test_warnings`, which says
    "call the function instead". That advice is right about the boundary and
    wrong about the fix — the assertion should not be in the suite at all — so
    this warning is worth its line beside it.
    """
    out: List[str] = []
    rng = _scope_range_re(config)
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        rel = _rel_display(path, repo_root)
        hit = next((n for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and rng.search(n.value)), None)
        if hit is not None:
            out.append(
                f"{rel}:{hit.lineno}: a hardcoded '{rng.search(hit.value).group(0)}' "
                f"range makes this test a diff-time scope claim — it asserts "
                f"what an item did NOT touch, which stops being true the moment "
                f"that item merges into the base, and is red by construction on "
                f"a stacked queue where the real base is the queue branch. "
                f"Declare the pinned file under '## Asserts against' in the item "
                f"spec and let 'aide scope' decide it on the claim branch "
                f"(conventions.md §1 → authorised-paths, §6)")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _SUBPROCESS_FUNCS:
                continue
            consts = [c.value for c in ast.walk(node)
                      if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            if not any("aide.py" in c for c in consts):
                continue
            if not any(c == "scope" or c.endswith(" scope") or " scope " in c
                       for c in consts):
                continue
            out.append(
                f"{rel}:{node.lineno}: shells out to 'aide scope' from the "
                f"suite — the verb resolves its base from the CURRENT branch's "
                f"recorded base, so this passes only while the suite runs on "
                f"the item's own claim branch and fails by construction in "
                f"the post-merge run of 'aide merge', from the merge target. "
                f"Scope is "
                f"checked on the branch, not asserted in the suite: declare the "
                f"pinned file under '## Asserts against' instead "
                f"(conventions.md §1 → authorised-paths, §6)")
            break
    return out


#: The subprocess entry points that can hand *decoded* text back to the caller.
#: `call` and `check_call` return an exit status and never a capture, so a
#: `text=` on one of those decodes nothing and flagging it would be exactly the
#: false positive that stops a lint being read.
_DECODING_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output"})

#: Both spellings of "decode this for me". `universal_newlines=` is the pre-3.7
#: name and is still accepted, so a lint that knows only `text=` sees half the
#: shape — and the older spelling is the one an author copies from an old
#: answer, which is where this class comes from in the first place.
_TEXT_MODE_KWARGS = frozenset({"text", "universal_newlines"})


def _subprocess_names(tree: ast.AST) -> Tuple[set, Dict[str, str]]:
    """How this module spells `subprocess`: `(module aliases, name -> real)`.

    Matching on the method name alone flags `Runner().run(text=True)`, which has
    nothing to do with `subprocess` — caught in review, and the reason the
    docstring below can claim precision it would otherwise only assert. Both
    import forms are followed, aliases included:

        import subprocess              -> {"subprocess"}
        import subprocess as sp        -> {"sp"}
        from subprocess import run     -> {"run": "run"}
        from subprocess import run as r-> {"r": "run"}

    A star import binds every name at once and is treated as binding exactly
    the ones this lint cares about — caught in review, where resolving imports
    had turned `from subprocess import *` from a reported call into a silent
    one. Trading a false positive for a false negative is the wrong direction
    here, and this section says why.

    A binding made any other way — `run = subprocess.run`, or the module object
    re-exported through a sibling (`from helpers import subprocess`) — is not
    followed, and the lint stays quiet on it rather than guessing.
    """
    modules: set = set()
    funcs: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name == "*":
                    funcs.update({f: f for f in _DECODING_SUBPROCESS_FUNCS})
                    continue
                funcs[alias.asname or alias.name] = alias.name
    return modules, funcs


def _asks_for_text(node: ast.Call) -> bool:
    """Does this call ask for decoded output, as far as the source can say?

    `text=False` and `universal_newlines=None` ask for bytes and are not the
    defect. Anything else — `True`, a name, an expression — is treated as
    asking, because a call that may decode and names no codec is wrong in
    exactly the way a call that certainly decodes is.
    """
    for kw in node.keywords:
        if kw.arg not in _TEXT_MODE_KWARGS:
            continue
        if isinstance(kw.value, ast.Constant) and not kw.value.value:
            continue
        return True
    return False


def subprocess_encoding_test_warnings(repo_root: Path,
                                      config: Dict[str, Dict[str, object]]) -> List[str]:
    """Tests decoding subprocess output with whatever codec the platform guesses.

    conventions.md §6: a test that captures subprocess output as text passes
    `encoding="utf-8"`. Without it Python decodes with
    `locale.getpreferredencoding()` — UTF-8 on a Linux runner, **cp1252** on a
    Windows one — so the same bytes become different strings on the two legs of
    the same CI run.

    The recorded instance is the reason this is a lint and not advice. Six
    items in one consumer queue independently wrote
    `subprocess.run(..., capture_output=True, text=True)`; all six passed the
    Linux-only validator, and `windows-latest` returned a `KeyError` on a
    cp1252-mangled em-dash heading in one test and — worse — an **emoji-diff
    guard that matched nothing and reported PASS** in another. The second is a
    false negative: a gate that reports green having verified nothing, which is
    the worst outcome this loop has available and is invisible to every gate
    inside it (§7). Six independent authors reproducing one shape in one queue
    is the signature of a missing rule, not of a careless author.

    Decidable by AST, in the same shape as the eol-pin lint next door: a call
    to `run` / `Popen` / `check_output` carrying a `text=` or
    `universal_newlines=` keyword and no `encoding=` keyword. Three narrowings
    put together mean every warning this emits names a call that really would
    decode — the function set above, a literal-false `text=`, and the call
    having to reach `subprocess` through an import this module actually makes
    (`_subprocess_names`), without which `Runner().run(text=True)` is reported
    for sharing a method name.

    **The limit, stated rather than left to be discovered:** only a direct
    call is seen. A project that has wrapped its subprocess calls in a helper
    — which is the fix a consumer reached for — presents one call site to this
    lint and silence for the rest, and a `**kwargs` spread hides the keyword
    entirely. Silence here means "no call of the recorded shape", never "this
    suite decodes safely".
    """
    out: List[str] = []
    for path in _test_files(repo_root, config):
        try:
            tree = ast.parse(path.read_text(encoding=_ENCODING))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        modules, funcs = _subprocess_names(tree)
        if not modules and not funcs:
            continue                      # this module never imports subprocess
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                # `subprocess.run(...)`, or whatever this module called it.
                if not (isinstance(func.value, ast.Name)
                        and func.value.id in modules):
                    continue
                name = func.attr
            elif isinstance(func, ast.Name):
                name = funcs.get(func.id, "")
            else:
                continue
            if name not in _DECODING_SUBPROCESS_FUNCS:
                continue
            if any(kw.arg == "encoding" for kw in node.keywords):
                continue
            if not _asks_for_text(node):
                continue
            out.append(
                f"{_rel_display(path, repo_root)}:{node.lineno}: captures "
                f"subprocess output as text with no encoding= — Python then "
                f"decodes with the platform's locale codec, UTF-8 here and "
                f"cp1252 on a Windows runner, which mangles non-ASCII and has "
                f"defeated a guard silently rather than failing. Pass "
                f'encoding="utf-8". See conventions.md §6')
            break
    return out


def _gitattributes_no_rewrite_patterns(repo_root: Path) -> Optional[List[str]]:
    """Every pattern in `.gitattributes` that stops the CRLF rewrite.

    ``None`` (not ``[]``) when the file is absent, so the caller can tell "no
    pins" from "no file" and say the more useful of the two.

    **Three spellings, not one.** `eol=lf` is the one §6 names, but `binary`
    (git's macro for `-text -diff`) and a bare `-text` both switch the
    conversion off outright, and a file under either is exactly as safe. Only
    accepting `eol=lf` made the lint warn about a `*.png binary` fixture and
    tell its author to add a pin that would be wrong for it — a wolf-cry on
    code that had already done the right thing, which is how a lint stops being
    read.
    """
    path = repo_root / ".gitattributes"
    if not path.is_file():
        return None
    out: List[str] = []
    try:
        text = path.read_text(encoding=_ENCODING)
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # `eol=lf` alone is enough: `text eol=lf` and a bare `eol=lf` both stop
        # core.autocrlf rewriting the file, which is the whole point here — as
        # do `binary` and an unsetting `-text`. A bare `text` is NOT in the
        # list: it *enables* the conversion.
        if len(parts) > 1 and any(a in ("eol=lf", "binary", "-text")
                                  for a in parts[1:]):
            out.append(parts[0])
    return out


def _gitattributes_matches(rel_posix: str, pattern: str) -> bool:
    """Does a `.gitattributes` pattern cover this repo-relative path?

    Git's pattern rules, not `fnmatch`'s: a `*` stops at a `/` (so
    `tests/*.json` must not match `tests/a/b.json`, which `fnmatch` would),
    `**` crosses separators, and a pattern with **no** slash matches at any
    depth — which is how `*.json` covers the whole tree.
    """
    pattern = pattern.strip().rstrip("/")
    if not pattern:
        return False
    if pattern.startswith("/"):
        pattern = pattern[1:]
    if "/" not in pattern:
        # basename match at any depth, per gitattributes(5)
        return _glob_segment(rel_posix.rsplit("/", 1)[-1], pattern)
    return _glob_path(rel_posix, pattern)


def _glob_segment(name: str, pattern: str) -> bool:
    """`fnmatch` on a single path component (no separators involved)."""
    return fnmatch.fnmatchcase(name, pattern)


def _glob_path(rel_posix: str, pattern: str) -> bool:
    """Match a path against a slash-aware glob, honouring `**`."""
    regex = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            regex.append("(?:.*/)?")     # zero or more leading directories
            i += 3
            continue
        if pattern.startswith("**", i):
            regex.append(".*")
            i += 2
            continue
        if ch == "*":
            regex.append("[^/]*")        # a single `*` never crosses a `/`
        elif ch == "?":
            regex.append("[^/]")
        elif ch == "/":
            regex.append("/")
        else:
            regex.append(re.escape(ch))
        i += 1
    return re.fullmatch("".join(regex), rel_posix) is not None


class _LiteralPathResolver(ast.NodeVisitor):
    """Module-level names whose value is a path built only from literals.

    Deliberately narrow. It follows exactly two roots — ``Path(__file__)``
    walked up with ``.parent`` / ``.parents[N]``, and a name this same module
    already resolved — joined with string literals via ``/``. Anything built at
    run time (a ``tmp_path`` fixture, a function argument, a constant imported
    from another package) resolves to nothing and is skipped, which is the
    point: those are not committed files, and guessing at them is how a lint
    starts crying wolf.
    """

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.names: Dict[str, Path] = {}

    def visit_Assign(self, node: ast.Assign) -> None:
        resolved = self._resolve(node.value)
        if resolved is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.names[target.id] = resolved

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # `GOLDEN: Path = REPO_ROOT / "x.json"` — annotated, same shape.
        if node.value is None or not isinstance(node.target, ast.Name):
            return
        resolved = self._resolve(node.value)
        if resolved is not None:
            self.names[node.target.id] = resolved

    def _resolve(self, node: ast.AST) -> Optional[Path]:
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left = self._resolve(node.left)
            if left is None:
                return None
            right = node.right
            if isinstance(right, ast.Constant) and isinstance(right.value, str):
                return left / right.value
            return None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            base = self._resolve(node.value)
            return None if base is None else base.parent
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "parents":
            base = self._resolve(node.value.value)
            index = node.slice
            if base is None or not isinstance(index, ast.Constant) \
                    or not isinstance(index.value, int):
                return None
            try:
                return base.parents[index.value]
            except IndexError:
                return None
        if isinstance(node, ast.Call):
            func = node.func
            # `.resolve()` / `.absolute()` are identity here: the file path this
            # walks from is already absolute.
            if isinstance(func, ast.Attribute) and func.attr in ("resolve", "absolute"):
                return self._resolve(func.value)
            if isinstance(func, ast.Name) and func.id == "Path" and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id == "__file__":
                    return self.file_path
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    candidate = Path(arg.value)
                    return candidate if candidate.is_absolute() else None
        return None


#: Attribute calls that read a file's exact bytes, or text that a byte-exact
#: golden comparison is one edit away from. `read_text()` is included because
#: its universal-newline translation only *hides* an unpinned CRLF checkout —
#: the consumer instance that prompted this had two such comparisons sitting
#: latent until someone switched them to `read_bytes()`.
_BYTE_EXACT_READS = ("read_bytes", "read_text")


def _read_call_name(node: ast.AST,
                    readers: Tuple[str, ...] = _BYTE_EXACT_READS
                    ) -> Optional[Tuple[str, int]]:
    """`(name, lineno)` if *node* is `NAME.read_bytes()` / `NAME.read_text()`.

    *readers* narrows which of the two counts. The comparison and hash sites
    pass `("read_text",)`: `read_bytes()` is collected unconditionally a few
    lines below, so letting them match it too appended every such read twice.
    Harmless downstream — the caller dedupes by resolved path — but the two
    rules are disjoint by construction and the code should say so.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in readers \
            and isinstance(func.value, ast.Name):
        return func.value.id, func.lineno
    return None


def _byte_exact_reads(tree: ast.AST) -> List[Tuple[str, int]]:
    """`(name, lineno)` for reads whose bytes are actually *compared*.

    The narrowing that keeps this lint worth reading. An earlier draft flagged
    every `NAME.read_text()` in the tests tree and, run against a real consumer,
    produced twenty-odd warnings of which the overwhelming majority were plain
    helper reads --

        def _read_progress() -> str:
            return _PROGRESS_PATH.read_text(encoding="utf-8")

    -- whose callers go on to assert a *substring*. Universal-newline
    translation makes those immune to the CRLF rewrite, so a pin buys them
    nothing and the warning is pure noise. Requiring the read to sit directly
    inside an equality comparison, or to be fed to a hash, is what separates
    `a.read_bytes() == golden.read_bytes()` from reading a file to look inside
    it. A read stored in a local and compared later is missed on purpose: that
    indirection is the shape of a determinism check between two generated
    files, which needs no pin at all.

    **The two readers are not equally safe, and the split above is drawn on
    exactly that** (issue #124). `read_text()` applies universal-newline
    translation, so a CRLF-rewritten file arrives with `\n` either way: a
    *parsed* text read — `json.loads`, a Markdown table walked cell by cell —
    is immune to the rewrite, and covering it would be wrong rather than merely
    noisy. `read_bytes()` translates nothing, so that immunity does not exist
    for it and **any** use of it on a committed path is byte-sensitive; the
    `\r` survives into whatever parses the result. Hence: `read_bytes()`
    anywhere counts, `read_text()` only where its result is compared or hashed.

    Review caught the earlier version of this docstring claiming the immunity
    for the whole "parses rather than byte-compares" class. It is a property of
    `read_text()`, not of parsing — measured: `p.read_bytes().decode()` on a
    CRLF checkout leaves `' value\r'` in the last cell of a Markdown row where
    `read_text()` leaves `' value'`.

    What stays silent is a `read_text()` parse, and that silence is still not
    coverage: the file may need a pin for a byte-reproducibility claim asserted
    somewhere this lint cannot see — a regenerate-and-diff, a digest kept
    elsewhere — and that claim is the project's to assert directly.
    """
    # Reads sitting directly under a membership or ordering test — `b"{" in
    # p.read_bytes()`. Kept exempt from the blanket `read_bytes()` rule below:
    # the needle is what decides there, and a literal one carrying no newline
    # is immune to the rewrite. Collected first because `ast.walk` reaches the
    # inner call without the Compare that gives it its meaning.
    loose_operands: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        sides = [node.left, *node.comparators]
        for i, side in enumerate(sides):
            # `a == b < c` is one node meaning `a == b and b < c`, so an
            # operand is exempt only when *neither* comparison it takes part
            # in is an equality. Judging the node as a whole exempted `b` here,
            # which really is on one side of an `==`.
            adjacent = [op for j, op in enumerate(node.ops) if j in (i - 1, i)]
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in adjacent):
                loose_operands.add(id(side))

    out: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        # `read_bytes()` in any other position. It translates nothing, so there
        # is no context in which the CRLF rewrite passes through it harmlessly
        # — the `\r` survives into whatever parses the result.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_bytes"
                and isinstance(node.func.value, ast.Name)
                and id(node) not in loose_operands):
            out.append((node.func.value.id, node.func.lineno))
            continue
        if isinstance(node, ast.Compare):
            # Only `==` / `!=`: an ordering or membership test on file contents
            # is not a byte-exactness claim.
            if not all(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for side in [node.left, *node.comparators]:
                found = _read_call_name(side, ("read_text",))
                if found is not None:
                    out.append(found)
        elif isinstance(node, ast.Call):
            func = node.func
            # `h.update(p.read_bytes())` and `hashlib.sha256(p.read_bytes())` --
            # a digest is a byte-exact claim by another name, and the recorded
            # whole-tree-hash failures took exactly this shape.
            is_hash_sink = (
                (isinstance(func, ast.Attribute)
                 and (func.attr == "update"
                      or func.attr.startswith(("sha", "md5", "blake"))))
                or (isinstance(func, ast.Name)
                    and func.id.startswith(("sha", "md5", "blake")))
            )
            if not is_hash_sink:
                continue
            for arg in node.args:
                found = _read_call_name(arg, ("read_text",))
                if found is not None:
                    out.append(found)
    return out


def gitattributes_eol_pin_warnings(repo_root: Path,
                                   config: Dict[str, Dict[str, object]]) -> List[str]:
    """Warn on a committed fixture compared byte-for-byte with no `eol=lf` pin.

    conventions.md §6 states the rule — *"a committed byte-exact fixture needs a
    `.gitattributes` `text eol=lf` pin"* — and until now nothing checked it.
    Without the pin, `core.autocrlf` rewrites the file on a Windows checkout and
    every byte comparison against it fails **on Windows only**, which is exactly
    the platform §7 says no gate in this loop ever sees. The recorded instance
    cost 13 red tests across three modules, invisible to every local run.

    **Precision over recall, deliberately.** The resolver follows only paths
    built from literals — `Path(__file__)` walked up, joined with string
    constants — so a fixture whose path arrives from a `tmp_path` fixture, a
    function argument or a constant imported from another package resolves to
    nothing and is skipped in silence. That is not a gap to be closed later by
    guessing: the overwhelming majority of `read_bytes()` calls in a real suite
    compare two *freshly generated* files to each other (a determinism check),
    and those need no pin at all. Flagging them would make the lint noise, and a
    lint that cries wolf stops being read. What remains — a literal path or an
    obvious glob beside a `read_bytes()` — is every instance recorded so far.

    A resolved path is only reported if it **exists** in the checkout, which is
    the cheap proxy for "committed": a path that resolves but is not there is a
    generated artifact, not a fixture.

    **Two causes of silence, and only one of them is the one above.** The first
    is resolution: a path this lint cannot follow is skipped. The second is
    shape, in `_byte_exact_reads` — a committed artifact whose tests
    `read_text()` and *parse* draws no warning whether or not it is pinned,
    because universal newlines make that read immune. The second is the one
    that misleads, because such a file looks exactly like the kind this lint
    exists for. Recorded (issue #124): a spec wrote "the eol-pin lint passes"
    as an acceptance criterion for a committed generated JSON artifact its
    tests `json.loads`; the criterion was vacuous by construction, and the pin
    had to be asserted by a project-side test instead. Read a warning here as
    authoritative and silence as *no reading taken*.
    """
    files = _test_files(repo_root, config)
    if not files:
        return []
    patterns = _gitattributes_no_rewrite_patterns(repo_root)
    out: List[str] = []
    seen: set = set()
    root = repo_root.resolve()
    for path in files:
        try:
            source = path.read_text(encoding=_ENCODING)
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        resolver = _LiteralPathResolver(path.resolve())
        resolver.visit(tree)
        if not resolver.names:
            continue
        for name, lineno in _byte_exact_reads(tree):
            target = resolver.names.get(name)
            if target is None:
                continue
            try:
                rel = target.resolve().relative_to(root)
            except ValueError:
                continue                      # outside the repo: not ours to pin
            if not target.exists():
                continue                      # generated, not committed
            rel_posix = rel.as_posix()
            key = (_rel_display(path, repo_root), rel_posix)
            if key in seen:
                continue
            seen.add(key)
            if patterns is None:
                out.append(
                    f"{_rel_display(path, repo_root)}:{lineno}: compares "
                    f"{rel_posix} byte-for-byte, but this repo has no "
                    f".gitattributes — on a Windows checkout core.autocrlf "
                    f"rewrites it and the comparison fails there and nowhere "
                    f"else. Add `{rel_posix} text eol=lf`. See conventions.md §6")
                continue
            if any(_gitattributes_matches(rel_posix, p) for p in patterns):
                continue
            out.append(
                f"{_rel_display(path, repo_root)}:{lineno}: compares "
                f"{rel_posix} byte-for-byte, but no .gitattributes `eol=lf` "
                f"pin covers it — on a Windows checkout core.autocrlf rewrites "
                f"it and the comparison fails there and nowhere else. Add "
                f"`{rel_posix} text eol=lf`. See conventions.md §6")
    return out


def nested_deliverable_warnings(lines: List[str]) -> List[str]:
    """Status-bearing bullets nested anywhere inside a stage section.

    The parser matches indented bullets, so a nested one counts as a full
    deliverable in the rollup and in item-status parsing. The nesting says
    "subordinate" to a reader while the tooling says "peer" — so a `📋` child
    quietly holds its ✅ parent's stage open, and nothing reconciles the two
    readings.

    **Scanned across the whole stage section, deliberately, not just the
    Deliverables block.** `stage_deliverable_statuses` reads `lines[start:end]`
    — every leading-icon bullet in the section, skipping only checkboxes — so an
    indented status bullet under **Acceptance** drags the stage exactly the same
    way. Verified: such a bullet turns `['complete']` into
    `['complete', 'planned']` and a ✅ stage into 🚧. Narrowing this to the
    Deliverables block would under-report a bullet that really does break the
    rollup.
    """
    out: List[str] = []
    for start, end, num in stage_sections(lines):
        for i in range(start, end):
            m = _NESTED_DELIVERABLE_RE.match(lines[i])
            if m:
                out.append(
                    f"progress.md:{i + 1}: stage {num} has a nested status bullet "
                    f"({m.group('icon')}) — the rollup counts it as a full "
                    f"deliverable despite the indent, so it can hold the stage "
                    f"open while reading as subordinate. Flatten it, or drop "
                    f"its icon.")
    return out


def unattributed_reference_warnings(lines: List[str]) -> List[str]:
    """Deliverable bullets that reference items but attribute none of them.

    Only a bullet's trailing ``*(Item NNN)*`` marker ties items to it (§1,
    issue #99). A bullet whose references all sit mid-prose therefore tracks
    nothing: the items it names stay planned, hold their queue open, and
    `aide progress set` cannot find the bullet — a silent gap unless it is
    reported where the author can fix it. A bullet that has a trailing marker
    is fine, whatever else its prose mentions: the prose is free text by
    design, not a mistake.
    """
    out: List[str] = []
    for start, last in _deliverable_bullet_spans(lines):
        if _bullet_marker_item_numbers(lines[last]):
            continue
        span_text = "\n".join(lines[start:last + 1])
        nums = sorted(set(_referenced_item_numbers(span_text)))
        if nums:
            listed = ", ".join(f"{n:03d}" for n in nums)
            out.append(
                f"progress.md:{start + 1}: deliverable bullet references "
                f"item(s) {listed} but ends with no *(Item NNN)* marker — only "
                f"the trailing marker ties an item to a bullet, so this bullet "
                f"tracks nothing and those items read as untracked. End it "
                f"with the marker (e.g. '. *(Item {nums[0]:03d})*').")
    return out


def _line_after_title(lines: List[str]) -> str:
    """The first content line after the `#` title, or "" if there is none.

    Two subtleties. A multi-line HTML comment must be skipped **whole** — only
    its opening line starts with `<!--`, so testing line-by-line lets its body
    read as content. And the search stops at the first line after the title
    rather than skipping further headings: "opens with a blockquote" means the
    next thing, so `# Title` / `## Intro` / `> …` does not satisfy it.
    """
    in_comment = False
    seen_title = False
    for line in lines:
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        if not stripped:
            continue
        if not seen_title:
            if stripped.startswith("#"):
                seen_title = True
            continue
        return stripped
    return ""


def header_blockquote_warnings(ddir: Path) -> List[str]:
    """Living documents that do not open with their header blockquote.

    The blockquote carries the document's place in the loop and what it derives
    from — structural facts a reader landing anywhere needs (conventions.md §1).
    """
    out: List[str] = []
    targets = [ddir / name for name in _BLOCKQUOTE_DOCS]
    for sub in ("queue", "items"):
        if (ddir / sub).is_dir():
            targets.extend(sorted((ddir / sub).glob("*.md")))
    for path in targets:
        if not path.is_file():
            continue
        first = _line_after_title(path.read_text(encoding=_ENCODING).splitlines())
        if not first.startswith(">"):
            # Relative to docs_dir, matching `progress.md:12` and `items/…`.
            rel = path.relative_to(ddir).as_posix()
            out.append(f"{rel}: no header blockquote — the line after the title "
                       f"should carry this document's place in the loop and what "
                       f"it derives from")
    return out


#: The vision sections `templates/vision.md` marks `MANDATORY`, minus Goals &
#: objectives, whose mandatory substance is the G-code table checked separately
#: — a heading over an empty section would satisfy a heading check while giving
#: the roadmap nothing to trace. Each entry: (heading text, why it is needed).
_VISION_MANDATORY_SECTIONS = (
    ("Guiding principles", "the validator checks implementation against these"),
    ("Out of scope", "the validator flags work that contradicts this"),
    ("Success criteria", "they define when the project is done"),
)


def _has_g_code_row(lines: List[str]) -> bool:
    """True when any table row's first cell names a vision G-code (`G1 …`).

    The shape both mandatory tables share: vision's objectives table and the
    roadmap's objective → stage coverage table each open every row with the
    G-code. Cell counts differ (3 and 2), so the first cell is the invariant.
    """
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if cells and re.match(r"G\d+\b", cells[0]):
            return True
    return False


def root_document_warnings(ddir: Path) -> List[str]:
    """Root documents missing the sections their templates mark MANDATORY.

    `templates/vision.md` annotates four sections `MANDATORY: validator
    checks…` and `templates/roadmap.md` two, and until issue #86 nothing
    verified any of them: a hand-written vision with none of the sections
    passed `aide check`, so the promise the annotations make was kept by no
    code. The observed failure is exactly that — a vision authored free-hand
    in a consumer, structurally plausible, checked by nobody.

    Headings are matched tolerantly (any level, the template's `2.` numbering
    optional, case-insensitive): the lint is for a *dropped* section, and a
    renumbered heading is not a dropped section.

    Warnings, not errors, matching the item specs' mandatory-Assumptions lint:
    root documents predating this check exist in real consumers, and an
    unattended run must not start failing over a document none of its items
    touch — the queue-boundary human reads warnings. A missing file is silent:
    a repo may adopt the CLI without the root documents (issue #57), and
    `create-progress` onward is where `progress.md` becomes a hard error.
    """
    out: List[str] = []
    vpath = ddir / "vision.md"
    if vpath.is_file():
        vtext = vpath.read_text(encoding=_ENCODING)
        for title, why in _VISION_MANDATORY_SECTIONS:
            if not re.search(rf"^#{{1,6}}\s*(?:\d+\.\s*)?{title}\b", vtext,
                             re.MULTILINE | re.IGNORECASE):
                out.append(f"vision.md: no '{title}' section — the template "
                           f"marks it MANDATORY: {why}")
        if not _has_g_code_row(vtext.splitlines()):
            out.append("vision.md: no G-code objectives table (rows opening "
                       "'| G1 |…') — the template marks it MANDATORY: the "
                       "roadmap and progress.md trace every stage back to "
                       "these codes")
    rpath = ddir / "roadmap.md"
    if rpath.is_file():
        rtext = rpath.read_text(encoding=_ENCODING)
        if not _has_g_code_row(rtext.splitlines()):
            out.append("roadmap.md: no objective → stage coverage rows "
                       "(opening '| G1 …|') — the template marks the table "
                       "MANDATORY: it is what shows every vision G-code "
                       "mapped to a stage")
        if not re.search(r"^#{1,6}\s*Stage\s+\d+", rtext,
                         re.MULTILINE | re.IGNORECASE):
            out.append("roadmap.md: no '## Stage N — Title' sections — the "
                       "template marks the shape MANDATORY: queues are scoped "
                       "to a stage and progress.md is generated from these "
                       "sections")
    return out


def item_spec_warnings(ddir: Path, ddir_rel: str = "docs/aide") -> List[str]:
    """Item specs that break the shapes §1 and §5 fix.

    Four rules: the `# Item NNN — Title` heading must agree with the filename
    (the status report parses the title from it); the header must carry NO
    status field (status lives only in progress.md, and a duplicate has no
    owner and only drifts); the **Assumptions** block is mandatory, since it
    is what the validator surfaces for audit; and no always-authorised path
    may sit under **Asserts against** — the loop itself edits those on every
    item (the mandatory status flip alone touches progress.md), so the pin can
    never hold and `aide scope` would fail the item on its routine
    bookkeeping. Pinning progress.md is the natural way to write an AC that
    reads a gate row, which is exactly why it needs a spec-time warning.

    *ddir_rel* is the docs dir as specs spell it in their repo-relative paths;
    `run_checks` passes the configured value, and the default matches the
    scaffolded `aide.toml`.

    The missing-Assumptions finding is reported as ONE aggregated line. Specs
    predating the rule are common — 32 of 112 in the consumer this was measured
    against — and 32 separate warnings would bury the substantive ones, which is
    the failure mode issue #13 was filed for.
    """
    idir = ddir / "items"
    if not idir.is_dir():
        return []
    always = _always_authorised_paths(ddir_rel)
    out: List[str] = []
    missing_assumptions: List[str] = []
    for path in sorted(idir.glob("*.md")):
        m = re.match(r"0*(\d+)", path.name)
        if not m:
            continue
        num = int(m.group(1))
        text = path.read_text(encoding=_ENCODING)
        if not re.search(rf"^#\s+Item\s+0*{num}\s*[—–-]\s*\S", text, re.MULTILINE):
            out.append(f"items/{path.name}: no '# Item {num:03d} — Title' heading "
                       f"matching the filename")
        head = text.split("\n---", 1)[0]
        # A FIELD, not bold emphasis. Two conditions keep this precise: the line
        # is part of the header blockquote, and a colon sits beside the bold —
        # inside it (`**Status:**`, the template's own spelling) or right after
        # (`**Status**:`). Matching bare `**Status**` anywhere would flag prose
        # that merely emphasises the word.
        sm = next((m for line in head.splitlines() if line.lstrip().startswith(">")
                   for m in [_ITEM_STATUS_FIELD_RE.search(line)] if m), None)
        if sm:
            out.append(f"items/{path.name}: header carries a '{sm.group('name')}' field — "
                       f"status lives only in progress.md; a duplicate has no owner "
                       f"and only drifts")
        if not re.search(r"^##\s+Assumptions", text, re.MULTILINE):
            missing_assumptions.append(f"{num:03d}")
        parsed = parse_authorised_paths(text)
        for pin in (parsed.asserts_against if parsed else []):
            if any(patterns_overlap(pin, a) for a in always):
                out.append(
                    f"items/{path.name}: '{pin}' is pinned under Asserts "
                    f"against, but every item is authorised to edit it — the "
                    f"status flip and the insight append are loop bookkeeping "
                    f"— so the pin can never hold and `aide scope` will report "
                    f"a contradiction on every run; put the read-only content "
                    f"check in an acceptance criterion's test instead")
        # Asserts against means pinned-NOT-changed — `aide scope` prints
        # exactly that — so a path the spec also authorises itself to change
        # is a contradiction authored into the spec: the moment the item uses
        # the authorisation, scope fails it with no spec-side fix visible
        # (issue #94). Exact double-listing only: a literal pin under a May
        # change glob is the legitimate carve-out shape ("I may edit docs/**
        # but not docs/api.md") and scope stays the judge of whether it held.
        # Silent narrowing, made loud where it is authored (issue #119): the
        # spans after a bullet's first are dropped, and so is anything on a
        # continuation line, so the item is authorised for less than its spec
        # says and only an `aide scope` FAIL much later reveals it.
        for declared, dropped in dropped_bullet_spans(text):
            shown = ", ".join(f"'{d}'" for d in dropped)
            out.append(
                f"items/{path.name}: the Authorised paths bullet for "
                f"'{declared}' also names {shown}, and `aide scope` reads none "
                f"of them — a bullet declares ONE path, the first backtick "
                f"span of its opening line, and a continuation line is not "
                f"read at all. Give each path its own bullet, or the item is "
                f"authorised for less than its spec says")
        may_normalised = {_strip_dot_slash(p.strip())
                         for p in (parsed.may_change if parsed else [])}
        for pin in (parsed.asserts_against if parsed else []):
            if _strip_dot_slash(pin.strip()) in may_normalised:
                out.append(
                    f"items/{path.name}: '{pin}' is listed under both May "
                    f"change and Asserts against — Asserts against means "
                    f"pinned-not-changed, so `aide scope` will report every "
                    f"change to it as a contradiction. If the item writes the "
                    f"file and its tests assert against the final state, list "
                    f"it only under May change and say so in prose")
    if missing_assumptions:
        shown = ", ".join(missing_assumptions[:8])
        more = (f" (+{len(missing_assumptions) - 8} more)"
                if len(missing_assumptions) > 8 else "")
        out.append(f"{len(missing_assumptions)} item spec(s) have no mandatory "
                   f"'## Assumptions' block: {shown}{more} — it is what the "
                   f"validator surfaces for audit at the queue boundary")
    return out


def _stray_icons_in_line(line: str) -> List[str]:
    """Status icons on this line that sit where one could plausibly be
    mistaken for a structural status declaration.

    conventions.md §1 is explicit that icons are read *only* at structural
    positions — a deliverable bullet's leading icon, a table row's last cell,
    a stage header's trailing icon — and that "an icon anywhere else […] is
    plain text and is never read as status, so authors need not avoid the
    icon vocabulary in free text." A bullet with no leading icon, or an
    ordinary paragraph, therefore has *no* structural position at all, and
    any icon it contains is exactly that free text — never stray. Only a
    heading, whose sole structural slot is the trailing icon, can still carry
    a status-shaped icon somewhere a reader would misread as the header's
    status.
    """
    icons = list(_ICON_RE.finditer(line))
    if not icons:
        return []
    if _QUEUE_STATUS_RE.match(line):
        return []  # "> **Status:** …" lines legitimately carry an icon
    if line.strip().startswith("|"):
        return []  # table rows: parsers read specific cells only, never prose
    if _BULLET_RE.match(line):
        return []  # bullets: only the leading icon is structural; the rest is free prose
    if re.match(r"^#{1,6}\s", line):  # any heading level may carry a trailing icon
        t = _TRAILING_ICON_RE.search(line)
        allowed = t.span(1) if t else None
        return [i.group(0) for i in icons if i.span() != allowed]
    return []  # ordinary paragraph text: no structural position exists here at all


def stray_icon_warnings(ddir: Path) -> List[str]:
    """Warn on status icons outside structural positions in the status-bearing
    documents (``progress.md`` and queue files).

    The parsers only ever read icons at structural positions (conventions.md
    §1), so a stray icon is never *misread* — this lint surfaces near-misses so
    the status documents stay unambiguous to human readers too. Other documents
    (vision, roadmap, item specs) are not scanned: nothing parses icons there,
    so their prose is free.
    """
    out: List[str] = []
    paths: List[Path] = []
    progress = ddir / "progress.md"
    if progress.is_file():
        paths.append(progress)
    paths.extend(iter_queue_paths(ddir / "queue"))
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding=_ENCODING).splitlines(), start=1):
            for icon in _stray_icons_in_line(line):
                out.append(
                    f"{path.relative_to(ddir).as_posix()}:{lineno}: status icon {icon} outside a "
                    f"structural status position (parsers treat it as plain text; move "
                    f"or remove it if status was intended)"
                )
    return out


def run_checks(repo_root: Path, config: Dict[str, Dict[str, object]],
               branches: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)``. Empty errors == pass.

    The first twelve checks all run before, and survive, the two early returns
    below, but for two different reasons. Six of them —
    `absolute_path_test_warnings`, `separator_dependent_test_warnings`,
    `cli_subprocess_test_warnings`, `subprocess_encoding_test_warnings`,
    `gitattributes_eol_pin_warnings`, `scope_claim_test_warnings` — read
    `tests_dir` and never touch `docs_dir`, so they are the ones that make this
    function worth calling in a repo with no document set. The other six *are* document checks; they
    simply find nothing to say when `docs_dir` is absent, so keeping them costs
    nothing and they still report on a `docs_dir` that exists but has no
    `progress.md`.

    Three cases, kept apart: a repo with **no `docs_dir` at all** gets the
    test-hygiene lints and passes; a `docs_dir` that **exists but is not a
    directory** is a misconfigured `aide.toml` and an error; and a `docs_dir`
    that is a directory but has **lost its `progress.md`** is the error it
    always was.
    """
    errors: List[str] = []
    warnings: List[str] = []
    ddir = docs_dir(repo_root, config)
    progress_path = ddir / "progress.md"

    errors.extend(template_residue_errors(ddir))
    warnings.extend(stray_icon_warnings(ddir))
    warnings.extend(insight_warnings(ddir))
    warnings.extend(absolute_path_test_warnings(repo_root, config))
    warnings.extend(separator_dependent_test_warnings(repo_root, config))
    warnings.extend(cli_subprocess_test_warnings(repo_root, config))
    warnings.extend(subprocess_encoding_test_warnings(repo_root, config))
    warnings.extend(gitattributes_eol_pin_warnings(repo_root, config))
    warnings.extend(scope_claim_test_warnings(repo_root, config))
    warnings.extend(header_blockquote_warnings(ddir))
    warnings.extend(root_document_warnings(ddir))
    # A docs_dir outside the repo falls back to its absolute spelling, which
    # cannot appear in a spec's repo-relative paths — the always-authorised
    # pin lint then has nothing to match; the other spec-shape lints still
    # apply.
    warnings.extend(item_spec_warnings(ddir, _rel_display(ddir, repo_root)))
    if ddir.exists() and not ddir.is_dir():
        # `docs_dir` pointing at something that is not a directory is a
        # misconfiguration, and a third case again: it is neither "no document
        # set" nor "a document set missing its progress.md". Left folded into
        # the partial-adoption branch below it would report "this repo has no
        # AIDE document set" and exit 0 — a typo in aide.toml passing as a
        # deliberate choice not to adopt the loop.
        errors.append(
            f"{_rel_display(ddir, repo_root)} is configured as docs_dir but is "
            f"not a directory — fix [project] docs_dir in aide.toml")
        return errors, warnings
    if not ddir.is_dir():
        # Two different situations used to produce one error. A repo with no
        # document set at all is not a broken loop repo — it is a repo that
        # adopted the conventions and the CLI without the roadmap documents,
        # and the document checks simply do not apply to it. Everything above
        # has already run and is kept: three of those lints read `tests_dir`,
        # not `docs_dir`, and conflating the two cases made them unreachable
        # for any such repo — this framework's own repository included, which
        # is where they were written (issue #57).
        return errors, warnings
    if not progress_path.is_file():
        # `docs_dir` exists but its central document does not: a real error.
        return [f"missing {progress_path}"], warnings
    # One read, reused: two reads can disagree if the file changes between them.
    text = progress_path.read_text(encoding=_ENCODING)
    lines = text.splitlines()
    warnings.extend(gate_warnings(lines))
    warnings.extend(nested_deliverable_warnings(lines))
    warnings.extend(unattributed_reference_warnings(lines))

    # Mandatory sections.
    has_stage_table = any(
        len(_split_row(l)) == 4 and re.fullmatch(r"\d+", _split_row(l)[0]) for l in lines
    )
    has_obj_table = any(
        len(_split_row(l)) == 3 and re.match(r"G\d+", _split_row(l)[0]) for l in lines
    )
    sections = stage_sections(lines)
    if not has_stage_table:
        errors.append("progress.md: missing Stage summary table")
    if not has_obj_table:
        errors.append("progress.md: missing Objective coverage table")
    if not sections:
        errors.append("progress.md: no '## Stage N' sections")

    # Summary row status vs. section header + rollup consistency.
    summary_status: Dict[str, str] = {}
    for l in lines:
        cells = _split_row(l) if l.strip().startswith("|") else []
        if len(cells) == 4 and re.fullmatch(r"\d+", cells[0]) and _icon_status(cells[3]):
            summary_status[cells[0]] = _icon_status(cells[3])

    section_nums = set()
    for start, end, num in sections:
        section_nums.add(num)
        header_status = _header_status(lines[start])
        derived = rollup_status(stage_deliverable_statuses(lines, start, end))
        summ = summary_status.get(num)
        if summ in ("deferred", "excluded"):
            continue
        if derived == "complete" and summ and summ != "complete":
            warnings.append(
                f"stage {num}: all deliverables ✅ but summary shows {summ} — "
                f"if the work shipped but the stage's goal is unmet, record the "
                f"goal as an Outcome target (❌ Not met) and close the stage; "
                f"stages track shipped work, targets track measured outcomes")
        if summ == "complete" and derived and derived != "complete":
            errors.append(f"stage {num}: summary marked ✅ but has non-complete deliverables")
        if header_status and summ and header_status != summ:
            warnings.append(f"stage {num}: header {header_status} disagrees with summary {summ}")

    for num in summary_status:
        if num not in section_nums:
            warnings.append(f"stage {num}: in summary table but has no '## Stage {num}' section")

    # Outcome targets: goal truth gates the OBJECTIVE rows. Claiming an
    # objective ✅ over an unmet target is the goal-level over-claim this
    # table exists to prevent (issue #14) — the mirror of the deliverable-level
    # error above.
    obj_status: Dict[str, str] = {}
    for l in lines:
        cells = _split_row(l) if l.strip().startswith("|") else []
        if len(cells) == 3 and re.match(r"G\d+", cells[0]) and _icon_status(cells[2]):
            obj_status[re.match(r"G\d+", cells[0]).group(0)] = _icon_status(cells[2])
    for t in outcome_targets(lines):
        if t.kind is None:
            warnings.append(
                f"progress.md:{t.lineno}: outcome target '{t.text}' has an "
                f"unrecognised Status (expected '✅ Met', '❌ Not met' or "
                f"'❓ Unverified')")
        for g in t.objectives:
            if obj_status.get(g) != "complete":
                continue
            if t.kind == "not-met":
                errors.append(
                    f"objective {g} marked ✅ but outcome target '{t.text}' "
                    f"is ❌ Not met")
            elif t.kind != "met":
                warnings.append(
                    f"objective {g} marked ✅ but outcome target '{t.text}' "
                    f"is not ✅ Met")

    # Queues: state is DERIVED from progress.md (open = any 📋/🚧 item); a
    # declared "> **Status:**" line is decorative — warn only when it lies.
    qdir = ddir / "queue"
    seen: Dict[int, str] = {}
    if qdir.is_dir():
        _, _, istat = _parse_item_status(lines)
        for qpath in iter_queue_paths(qdir):
            qtext = qpath.read_text(encoding=_ENCODING)
            derived_open = queue_is_open(qtext, istat)
            declared = queue_status(qtext)
            if declared:
                declared_live = declared.lower().startswith("live")
                if declared_live and not derived_open:
                    warnings.append(
                        f"{qpath.name}: declares 'Live' but every item is finished — "
                        f"state is derived from progress.md; run 'aide queue tidy' "
                        f"or drop the decorative Status line")
                elif not declared_live and derived_open:
                    warnings.append(
                        f"{qpath.name}: marked completed but still has open items "
                        f"in progress.md")
            for n in queue_item_numbers(qtext):
                if n in seen and seen[n] != qpath.name:
                    errors.append(f"item {n:03d} appears in both {seen[n]} and {qpath.name}")
                seen[n] = qpath.name

    # Item spec files: no duplicate numbers.
    idir = ddir / "items"
    if idir.is_dir():
        spec_nums: Dict[int, str] = {}
        for ipath in sorted(idir.glob("*.md")):
            m = re.match(r"0*(\d+)", ipath.name)
            if not m:
                continue
            n = int(m.group(1))
            if n in spec_nums:
                errors.append(f"duplicate item spec number {n:03d}: {spec_nums[n]} and {ipath.name}")
            spec_nums[n] = ipath.name

    # Claim-branch <-> status agreement (best effort).
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    if branches is None:
        branches = _list_claim_branches(repo_root, prefix)
    _, _, item_status = _parse_item_status(lines)
    unpublished = (set(_unpublished_branches(repo_root, config, prefix))
                   if branches else set())
    for br in branches:
        n = _branch_item_number(br, prefix)
        if br in unpublished:
            # Read against the last fetch, like every other remote question
            # here, and a warning rather than an error for that reason.
            warnings.append(
                f"unpublished branch {br}: this checkout has it and origin "
                f"does not, so it is invisible to every other checkout — a "
                f"failed 'aide claim' or 'aide queue start' push is the usual "
                f"cause. Publish it ('git push -u origin {br}') or delete it.")
        if n is None:
            # Not a claim branch. A queue branch is expected and silent; anything
            # else carrying the prefix is reported rather than ignored, so a real
            # stale claim named unconventionally cannot hide behind the anchor.
            if not _is_queue_branch(br, prefix):
                warnings.append(
                    f"unrecognised branch {br}: carries the claim prefix but is "
                    f"not '{prefix}NNN-short-name' (conventions.md §4), so no "
                    f"item status is tracked for it — rename it to the claim "
                    f"shape, or once it is merged run 'aide gc --merged' to "
                    f"delete it")
            continue
        # 🔍 is deliberately NOT reported: a claim branch whose item is awaiting
        # review is a normal, correct state, and warning about it on every run
        # until the human merges is how a real warning gets tuned out.
        if item_status.get(n) == "complete":
            warnings.append(f"stale claim branch {br}: item {n:03d} is already ✅")

    return errors, warnings


def _parse_item_status(lines: List[str]) -> Tuple[List[str], List[str], Dict[int, str]]:
    """Map item number -> most-advanced status found on its deliverable bullets.

    The only structural status declaration (conventions.md §1) is a deliverable
    bullet's leading icon — a line matching ``_BULLET_RE`` — together with any
    of its wrapped continuation lines (indented text carrying no bullet marker
    of its own). A reference anywhere else — a table cell, an acceptance
    checkbox, an ordinary paragraph — is free text and is never read as status,
    however many item numbers it happens to name (issue #15): a verification
    table's Notes column narrating what went wrong with several items, or a
    checkbox that merely cites the item that satisfies it, must not pull that
    item's tracked status backwards.

    Within a bullet, only the trailing ``*(Item NNN)*`` marker attributes — §1
    already calls it "the suffix [that] ties an item to the bullet". A
    reference form elsewhere in the bullet's prose is as free as one in a
    table cell: a ✅ bullet whose text mentions a live sibling ("absorbing
    *(Item 095)*'s scope") used to mark that sibling complete, overriding its
    own 📋 bullet — and once spent items were discounted from the cross-spec
    checks, the mis-attribution silenced exactly the pre-build errors the
    checks exist to raise (issue #99).
    """
    item_status: Dict[int, str] = {}
    for start, last in _deliverable_bullet_spans(lines):
        bullet_status = ICON_TO_STATUS[_BULLET_RE.match(lines[start]).group("icon")]
        for num in _bullet_marker_item_numbers(lines[last]):
            if num not in item_status or RANK[bullet_status] > RANK[item_status[num]]:
                item_status[num] = bullet_status
    return [], [], item_status


# --------------------------------------------------------------------------- #
# git plumbing
# --------------------------------------------------------------------------- #
def git(args: List[str], repo_root: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run git and hand back its output decoded as UTF-8, never as the locale.

    conventions.md §6, applied to the engine that states it. `text=True` alone
    decodes with `locale.getpreferredencoding()` — cp1252 on a Windows
    consumer — so a branch name, a changed path or a commit subject carrying a
    non-ASCII character came back as different characters there than here, and
    a prefix match against it quietly stopped matching. Git speaks UTF-8 for
    refs and paths, so this says so.

    `errors="replace"` rather than strict: a stray byte in one branch name must
    not raise out of `aide claim`. The replacement character fails the same
    match a mangled one did, and does it identically on every platform.
    """
    return subprocess.run(
        ["git", *args], cwd=str(repo_root), check=check,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )


def _push_new_branch(repo_root: Path, branch: str) -> Optional[str]:
    """``git push -u origin <branch>``: None on success, else a sentence.

    Three verbs publish a branch they have just created — `queue start`,
    `claim`, and `merge` under `pr` mode — and all three pushed with git()'s
    default `check=True`, so every cause of a failed push (no remote at all,
    origin unreachable, expired credentials, a rejecting server-side hook)
    left `main()` on a `CalledProcessError`: a raw traceback in a flow whose
    whole point is to run unattended. `cmd_queue_start` guarded exactly one
    cause in prose — the branch already on origin — and let the rest crash.

    The push is the *last* thing each of those verbs does, so its local half is
    already on disk when it fails. Handing back git's own words lets each
    caller say what survives and how to finish it by hand, which is the
    difference between a stall a person can act on and a stack trace.
    """
    res = git(["push", "-u", "origin", branch], repo_root, check=False)
    if res.returncode == 0:
        return None
    detail = (res.stderr.strip() or res.stdout.strip()
              or f"git exited {res.returncode} without a message")
    return f"pushing {branch} to origin FAILED:\n{detail}"


def _list_claim_branches(repo_root: Path, prefix: str) -> List[str]:
    if not (repo_root / ".git").exists():
        return []
    try:
        out_local = git(["branch", "--format=%(refname:short)"], repo_root, check=False).stdout
        out_remote = git(["branch", "-r", "--format=%(refname:short)"], repo_root, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names: List[str] = []
    for line in (out_local + out_remote).splitlines():
        name = line.strip()
        short = name.split("/", 1)[1] if name.startswith("origin/") else name
        if short.startswith(prefix):
            names.append(short)
    return sorted(set(names))


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Cross-spec queue check — do a queue's specs conflict, before any is built?
# --------------------------------------------------------------------------- #
class SpecFinding(NamedTuple):
    """One cross-item conflict between the specs on a queue."""

    severity: str          # "error" | "warning"
    kind: str              # machine-readable class, for the --report seam
    items: Tuple[int, ...]
    message: str


def patterns_overlap(a: str, b: str) -> bool:
    """True when two ``## Authorised paths`` patterns can cover the same file.

    Deliberately decides only the cases a script *can* decide: an identical
    pattern, a subtree wildcard swallowing the other, and a literal path
    covered by the other's glob. Two unrelated globs that would happen to
    intersect on some file neither spec has thought of are not modelled —
    reporting those would mean guessing at a future tree, and this check exists
    to be trusted, not to be argued with.
    """
    a = _strip_dot_slash(a.strip())
    b = _strip_dot_slash(b.strip())
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith("/**"):
            prefix = x[: -len("/**")]
            if y == prefix or y.startswith(prefix + "/"):
                return True
    if not any(c in a for c in "*?[") and path_matches(a, b):
        return True
    if not any(c in b for c in "*?[") and path_matches(b, a):
        return True
    return False


def _built_after(graph: Dict[int, List[int]]) -> Dict[int, Set[int]]:
    """For each item, every item it is built *after* — its declared
    dependencies and theirs, transitively.

    The ordering `## Dependencies` actually promises. Direct listing is not
    enough on its own: an item that names one sibling which in turn names
    another is built after both, and the pair the caller is about to judge may
    be the far end of that chain.

    Cycle-safe by the `in out` guard rather than by trusting the graph — a
    mutual pair is a real shape here (`_dependency_cycles` reports it as the
    error it is) and must not hang the check that discovers it.
    """
    closure: Dict[int, Set[int]] = {}
    for node in graph:
        out: Set[int] = set()
        stack = list(graph.get(node, []))
        while stack:
            dep = stack.pop()
            if dep in out:
                continue
            out.add(dep)
            stack.extend(graph.get(dep, []))
        out.discard(node)
        closure[node] = out
    return closure


def _dependency_cycles(graph: Dict[int, List[int]]) -> List[List[int]]:
    """Every dependency cycle in *graph*, each reported once.

    A cycle deadlocks `aide claim` outright: every item in it is blocked by
    another item in it, so none is ever claimable and the queue silently stops
    producing work rather than failing.
    """
    cycles: List[List[int]] = []
    seen: set = set()
    state: Dict[int, int] = {}   # 0 = visiting, 1 = done

    def walk(node: int, stack: List[int]) -> None:
        state[node] = 0
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 0:
                cycle = stack[stack.index(nxt):]
                key = tuple(sorted(cycle))
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif nxt not in state and nxt in graph:
                walk(nxt, stack)
        stack.pop()
        state[node] = 1

    for node in sorted(graph):
        if node not in state:
            walk(node, [])
    return cycles


def queue_spec_findings(repo_root: Path, config: Dict[str, Dict[str, object]],
                        number: int) -> Tuple[List[SpecFinding], List[int]]:
    """``(findings, unspecced)`` for every spec on queue *number*.

    Runs in the window `/aide-spec-queue` creates and currently leaves
    unguarded: N specs authored on one branch before any is built, where every
    cross-item conflict is both possible and cheap to fix. The invariant it
    enforces is the one a consumer's post-mortem arrived at — *predicting the
    one collision a spec happens to name is not the same as proving no sibling
    assertion depends on state this item's authorised edit changes.*
    """
    ddir = docs_dir(repo_root, config)
    qdir = ddir / "queue"
    qpath = queue_path(qdir, number)
    if qpath is None:
        return ([SpecFinding("error", "missing-queue", (),
                             f"no {queue_name(number)} file under "
                             f"{_rel_display(qdir, repo_root)}")],
                [])

    numbers = queue_item_numbers(qpath.read_text(encoding=_ENCODING))
    idir = ddir / "items"
    findings: List[SpecFinding] = []
    unspecced: List[int] = []
    declared: Dict[int, AuthorisedPaths] = {}

    # A finding against a SPENT item — merged (✅) or excluded (❌) — is an
    # error no later item can clear: the spec is a record nobody may edit, a
    # merged May-change claim can neither be harmed by a later writer nor harm
    # one, and an excluded item is never offered. Such findings are reported
    # for the rest of the queue's life, which teaches a reader to skim the run
    # where one is real — so spent items are discounted below, on both sides
    # of every comparison. Deferred (⏸️) items are NOT spent: their claims are
    # dormant, not dead, and a conflict with one is worth surfacing while
    # re-planning is still cheap.
    item_status = _progress_item_status(repo_root, config)
    spent = {n for n in numbers
             if item_status.get(n, "planned") in ("complete", "excluded")}

    for num in numbers:
        specs = item_spec_paths(idir, num)
        if not specs:
            # Normal mid-queue state, not a conflict: /aide-spec-queue exists to
            # fill these. Counted and reported, never silently dropped.
            unspecced.append(num)
            continue
        parsed = parse_authorised_paths(specs[0].read_text(encoding=_ENCODING))
        rel = _rel_display(specs[0], repo_root)
        if declares_nothing(parsed):
            if num not in spent:
                # A spent spec with no scope section merged (or was dropped)
                # regardless; the remedy the message names is no longer
                # available, so the warning would be pure unclearable noise.
                findings.append(SpecFinding(
                    "warning", "undeclared-scope", (num,),
                    f"item {num:03d} ({rel}) declares no '## Authorised paths' — its "
                    f"scope cannot be compared with its siblings'. Add the section "
                    f"(conventions.md §1); until then this item needs a human scope "
                    f"review, and `aide scope` cannot check it either"))
            continue
        declared[num] = parsed

    # Read once, used twice: the declared ordering exempts pinned-state pairs
    # below, and the same edges are the cycle graph further down. Reading each
    # spec's Dependencies section twice would be the only alternative.
    deps_by_item = {num: _item_dependencies(repo_root, config, num)
                    for num in numbers if num not in unspecced}
    # An item is built after everything it declares a dependency on, and after
    # what those declare in turn — but only along edges that still ORDER the
    # two items. A dependency `aide claim` no longer waits for does not hold
    # its dependent back: a ⏸️ deferred blocker is skipped by `_pick_item`, so
    # the dependent is claimable today and would pin a tree the deferred item
    # has not touched yet. Filtering the edges rather than the pairs also
    # settles the transitive case, where the link that fails to hold is an
    # intermediate: `b → c (⏸️) → a` leaves b free to build before a.
    ordering_edges = {num: [d for d in deps
                            if item_status.get(d, "planned") in BLOCKING_STATUSES]
                      for num, deps in deps_by_item.items()}
    built_after = _built_after(ordering_edges)

    # The loop bookkeeping every item writes anyway (`aide scope` authorises
    # these without them being listed). Specs often list them redundantly, and
    # two items "conflicting" over progress.md is not a conflict — it is the
    # claim protocol working. Excluded from the overlap check, never from the
    # pinned-state check: pinning progress.md would be a real assertion.
    ddir_rel = _rel_display(ddir, repo_root)
    bookkeeping = set(_always_authorised_paths(ddir_rel))

    ordered = sorted(n for n in declared if n not in spent)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            # Row 1 — two items claim edit rights on the same file.
            for pa in declared[a].may_change:
                if pa in bookkeeping:
                    continue
                for pb in declared[b].may_change:
                    if patterns_overlap(pa, pb):
                        findings.append(SpecFinding(
                            "warning", "may-change-overlap", (a, b),
                            f"items {a:03d} and {b:03d} both claim '{pa}'"
                            + (f" / '{pb}'" if pa != pb else "")
                            + " under May change — whichever builds second "
                              "inherits the first's edits; confirm that is intended"))
        # Rows 2+3 — one item may change what another pins. Under the
        # `## Authorised paths` vocabulary these are one check: an "Asserts
        # against" entry covers a byte-hash pin and a live recomputation alike,
        # which is the point — the live-recomputed case is the one a survey
        # hunting fragile-looking hashes missed.
        for b in ordered:
            if a == b:
                continue
            if a in built_after.get(b, ()):
                # Item a still holds item b back — b declares a dependency on
                # it, directly or through a chain, along links that all still
                # order (`ordering_edges`). So b is authored and built against
                # a tree that already holds a's edit: a landing cannot break a
                # pin b writes afterwards, by construction. This is the whole shape
                # of a `Validate stage N` item — it exists to pin the artifacts
                # its stage's items produce, and it names them as dependencies
                # — which made the error fire against every such item, with
                # neither remedy the message offers available: widening the pin
                # drops what the item exists to observe, and narrowing the
                # earlier edits removes the stage's whole point. A pair with no
                # declared dependency keeps the error: an undeclared ordering
                # is exactly what this check exists to find.
                continue
            for pa in declared[a].may_change:
                for pb in declared[b].asserts_against:
                    if patterns_overlap(pa, pb):
                        findings.append(SpecFinding(
                            "error", "changes-pinned-state", (a, b),
                            f"item {a:03d} may change '{pa}', which item {b:03d} "
                            f"pins as '{pb}' under Asserts against — item {b:03d}'s "
                            f"assertion breaks when item {a:03d} lands. Decide now "
                            f"which side is wrong: widen the pin, narrow the edit, "
                            f"or — if item {b:03d} is meant to be built after item "
                            f"{a:03d} and to pin what it produced — say so under "
                            f"item {b:03d}'s '## Dependencies', which both orders "
                            f"the queue and retires this finding"))

    # Row 5 — the dependency graph. A cycle deadlocks `aide claim`: every item
    # in it is blocked by another in it, so the queue silently stops producing
    # work rather than failing. The graph holds only items that can still
    # block a claim — the same status set `_pick_item` treats as blocking: a
    # complete, excluded or deferred dependency does not block, and such an
    # item is never offered, so no cycle through one can deadlock (a cycle
    # whose members all merged has PROVED its order was satisfiable). The typo
    # pass below shares the filter: a mistyped dependency in a spent or
    # deferred item's spec blocks nothing today, and the warning about it
    # would be unclearable.
    graph = {num: deps for num, deps in deps_by_item.items()
             if item_status.get(num, "planned") in BLOCKING_STATUSES}
    for cycle in _dependency_cycles(graph):
        chain = " → ".join(f"{n:03d}" for n in cycle + [cycle[0]])
        findings.append(SpecFinding(
            "error", "dependency-cycle", tuple(cycle),
            f"dependency cycle {chain} — every item in it is blocked by another "
            f"in it, so `aide claim` will never offer any of them"))

    known = set(numbers)
    for num, deps in graph.items():
        for dep in deps:
            if dep in known:
                continue
            has_spec = bool(item_spec_paths(idir, dep))
            in_a_queue = any(dep in queue_item_numbers(p.read_text(encoding=_ENCODING))
                             for p in iter_queue_paths(ddir / "queue"))
            if not has_spec and not in_a_queue:
                findings.append(SpecFinding(
                    "warning", "unknown-dependency", (num, dep),
                    f"item {num:03d} depends on item {dep:03d}, which has no spec "
                    f"and appears in no queue — a typo here blocks the item forever"))

    return findings, unspecced


def _write_findings_report(path: Path, number: int,
                           findings: List[SpecFinding],
                           unspecced: List[int]) -> None:
    """Write the machine-readable report — the seam a reviewer pass consumes as
    its worklist rather than re-deriving what this check already decided."""
    payload = {
        "queue": number,
        "unspecced_items": unspecced,
        "findings": [
            {"severity": f.severity, "kind": f.kind,
             "items": list(f.items), "message": f.message}
            for f in findings
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Plain utf-8, NOT `_ENCODING`: that is utf-8-sig, which writes a BOM. A BOM
    # is right for the markdown documents (Windows editors add one and the
    # parsers must tolerate it) and wrong here — `json.loads` rejects a leading
    # BOM outright, so the seam would be unreadable by the very consumer it
    # exists for.
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def cmd_check(args: argparse.Namespace) -> int:
    """The consistency gate over the document set — and two writes.

    One is asked for by flag: ``--report PATH`` writes the cross-spec findings
    file for `spec-reviewer`. The other is ``ensure_insights_inbox``: a
    ``docs_dir`` that exists but has no ``insights.md`` gets one, byte-exact
    from the template, committed where git allows, and the run says so in a
    ``notice:``. It is the engine keeping §1's promise that capture is a plain
    append to a file that exists, placed in the verb every consumer is told to
    run before its first unattended run. The exit code never depends on it:
    the creation cannot fail a run — a commit that git refuses, or a ``git``
    that cannot be run, is a sentence in the notice, not an error — and a
    document set whose inbox already exists is reported exactly as before.
    """
    queue = getattr(args, "queue", None)
    if getattr(args, "report", None) and queue is None:
        # Silently ignoring it would be worse than refusing: the caller asked
        # for a file that would never appear, and only the missing file would
        # ever say so.
        print("aide check: --report needs --queue; there are no cross-spec "
              "findings to report without one", file=sys.stderr)
        return 2

    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    ddir = docs_dir(repo_root, config)
    # Before the checks, so the file they then shape-check is the one that
    # exists — a run that created the inbox and warned about its absence in
    # the same breath would be reporting on two different repositories.
    ensure_insights_inbox(repo_root, config, verb="check")
    errors, warnings = run_checks(repo_root, config)

    if not ddir.exists() and queue is None:
        # A notice, not a warning: nothing is wrong, but the reader must not
        # read "OK" as "the documents were checked and are fine".
        #
        # Only on a non-`--queue` run. `--queue` sends `queue_spec_findings`
        # looking for a queue file under the same absent directory, so it runs
        # and errors — and "only the repo-agnostic checks ran" would be false
        # next to that error. The notice exists to stop a *pass* being
        # over-read; a run that fails needs no such guard.
        print(f"notice: no {_rel_display(ddir, repo_root)}/ — this repo has no "
              f"AIDE document set, so only the repo-agnostic checks ran")

    if queue is not None:
        findings, unspecced = queue_spec_findings(repo_root, config, queue)
        for f in findings:
            (errors if f.severity == "error" else warnings).append(f.message)
        if unspecced:
            listed = ", ".join(f"{n:03d}" for n in unspecced)
            print(f"aide check: queue {queue:03d} — {len(unspecced)} item(s) "
                  f"not yet specced, so not compared: {listed}")
        report = getattr(args, "report", None)
        if report:
            _write_findings_report(Path(report), queue, findings, unspecced)
            print(f"aide check: wrote {report}")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"aide check: FAIL ({len(errors)} error(s), {len(warnings)} warning(s))")
        return 1
    print(f"aide check: OK ({len(warnings)} warning(s))")
    return 0


def set_gate_status(text: str, index: int, kind: str,
                    note: Optional[str] = None, today: Optional[str] = None) -> str:
    """Resolve the *index*-th (1-based) row of the ``## Human gates`` table.

    Writes the decision and the date into the Status cell, and *note* into the
    last cell. Raises ``ValueError`` for a missing table or an out-of-range
    index — a typo must not pass as a silent no-op, which is exactly how a
    hand-edited gate went wrong before there was a verb for it.
    """
    lines = text.splitlines()
    gates = human_gates(lines)
    if not gates:
        raise ValueError("no '## Human gates' table in progress.md")
    if not 1 <= index <= len(gates):
        raise ValueError(f"there are {len(gates)} human gate(s); {index} is out of range")
    gate = gates[index - 1]
    if note and ("|" in note or "\n" in note or "\r" in note):
        raise ValueError(
            "the note may not contain '|' or a line break — either breaks the "
            "row's shape, and a row the parser cannot read is skipped, making a "
            "still-blocking gate silently disappear")
    icon = {"approved": "✅ Approved", "declined": "❌ Declined"}[kind]
    import datetime as _dt
    stamp = today or _dt.date.today().isoformat()
    i = gate.lineno - 1
    cells = _split_row(lines[i])
    cells[2] = f"{icon} ({stamp})"
    if note:
        cells[3] = note
    lines[i] = "| " + " | ".join(cells) + " |"
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def cmd_gate(args: argparse.Namespace) -> int:
    """List or resolve the human gates in progress.md.

    Resolving a gate is a **person's** act. No agent may run `approve` or
    `decline`: a gate exists precisely because the decision is not derivable
    from the work, so an agent resolving one destroys the only thing it was
    protecting.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    ppath = docs_dir(repo_root, config) / "progress.md"
    if not ppath.is_file():
        print(f"aide gate: missing {ppath}", file=sys.stderr)
        return 2
    text = ppath.read_text(encoding=_ENCODING)
    gates = human_gates(text.splitlines())

    if args.action == "list":
        if not gates:
            print("aide gate: no '## Human gates' table (nothing gated)")
            return 0
        for n, g in enumerate(gates, start=1):
            reach = g.reach
            mark = {"approved": "✅", "declined": "❌", "awaiting": "⏳"}.get(g.kind, "⚠")
            print(f"  {n}. {mark} {g.text} — blocks {reach}")
        outstanding = len(blocking_gates(text.splitlines()))
        print(f"aide gate: {len(gates)} gate(s), {outstanding} still blocking")
        return 0

    if args.number is None:
        print(f"aide gate: '{args.action}' needs a gate number — see `aide gate list`",
              file=sys.stderr)
        return 2
    kind = "approved" if args.action == "approve" else "declined"
    try:
        updated = set_gate_status(text, args.number, kind, args.note)
    except ValueError as exc:
        print(f"aide gate: {exc}", file=sys.stderr)
        return 2
    # NOT _ENCODING: "utf-8-sig" *strips* a BOM on read but *writes* one, so
    # passing it here made every gate decision prepend U+FEFF to progress.md —
    # manufacturing the exact hazard that constant exists to absorb. Every
    # other writer in this module already writes plain "utf-8"; this was the
    # one outlier. Read tolerantly, write clean.
    ppath.write_text(updated, encoding="utf-8")
    print(f"gate {args.number}: {kind}")
    if not args.no_commit:
        _commit_progress_file(repo_root, config,
                              f"docs: human gate {args.number} {kind}")
    return 0


#: What `aide progress set` accepts, and the tracked status each records.
#: `done` stays the word for ✅ — a consumer's muscle memory and every existing
#: runbook use it — and `in-review` is additive.
_SET_STATUS_MAP = {"in-progress": "in-progress", "in-review": "in-review",
                   "done": "complete"}


def cmd_progress(args: argparse.Namespace) -> int:
    if args.action == "accept":
        return _cmd_progress_accept(args)
    if args.action != "set":
        print("usage: aide progress set NNN <in-progress|in-review|done>", file=sys.stderr)
        return 2
    if args.status is None:
        print("usage: aide progress set NNN <in-progress|in-review|done>", file=sys.stderr)
        return 2
    if args.status not in _SET_STATUS_MAP:
        print("status must be 'in-progress', 'in-review' or 'done'", file=sys.stderr)
        return 2
    status_map = _SET_STATUS_MAP
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    progress_path = docs_dir(repo_root, config) / "progress.md"
    if not progress_path.is_file():
        print(f"error: {progress_path} not found", file=sys.stderr)
        return 1
    text = progress_path.read_text(encoding=_ENCODING)
    original = text
    # An item is only trackable if some deliverable bullet's trailing marker
    # names it — the ownership rule set_item_status flips by — otherwise the
    # set would be a silent no-op. A prose mention on someone else's bullet
    # does not count (issue #99). When the queue back-fill was missed,
    # self-heal deterministically from the item spec's own Stage/title header;
    # only when that context is missing too does this stay a loud, blocking
    # error.
    healed_note: Optional[str] = None
    if args.number not in _parse_item_status(text.splitlines())[2]:
        stage, title = _spec_stage_and_title(repo_root, config, args.number)
        healed = insert_item_reference(text, args.number, stage, title) if stage and title else None
        if healed is None:
            print(
                f"item {args.number:03d}: ERROR — no deliverable in progress.md "
                f"references 'Item {args.number:03d}', and no item spec with a "
                f"Stage header was found to insert one from; status NOT "
                f"recorded. Add the reference to the owning stage's deliverable "
                f"bullet (e.g. '- 📋 <deliverable>. *(Item {args.number:03d})*'), "
                f"then re-run.",
                file=sys.stderr,
            )
            return 1
        text = healed
        # Announced only after the guard below confirms the back-fill took —
        # a success-flavoured line right before "NOT changed" reads as a
        # contradiction in an unattended log.
        healed_note = (f"item {args.number:03d}: back-filled missing "
                       f"deliverable reference under Stage {stage} "
                       f"(from the item spec)")
    updated = set_item_status(text, args.number, status_map[args.status])
    if args.number not in _parse_item_status(updated.splitlines())[2]:
        # Belt to the heal's braces: if the back-fill (or anything else) left
        # no bullet whose trailing marker names this item, the set recorded
        # nothing — say so and write nothing, instead of printing success over
        # a silent no-op (the failure shape a review of issue #99 found).
        print(
            f"item {args.number:03d}: ERROR — after the back-fill, no "
            f"deliverable bullet's trailing *(Item {args.number:03d})* marker "
            f"names this item, so the status could not be recorded; progress.md "
            f"NOT changed. Add the marker to the owning bullet's last line, "
            f"then re-run.",
            file=sys.stderr,
        )
        return 1
    if healed_note:
        print(healed_note)
    if updated == original:
        print(f"item {args.number:03d}: no change (already >= {args.status})")
    else:
        progress_path.write_text(updated, encoding="utf-8")
        print(f"item {args.number:03d}: set to {args.status}")
    if not args.no_commit and (repo_root / ".git").exists():
        _commit_progress(repo_root, config, args.number, args.status)
    return 0


def _cmd_progress_accept(args: argparse.Namespace) -> int:
    """``aide progress accept STAGE --criterion N`` — tick an acceptance box.

    The explicit counterpart to the auto-tick ``set_item_status`` used to
    perform. An acceptance criterion is attested by a human who checked it, so
    it takes a deliberate command that records what was accepted and, with
    ``--evidence``, on what basis.
    """
    if args.criterion is None and not args.all_criteria:
        print("usage: aide progress accept STAGE (--criterion N | --all) "
              "[--evidence TEXT]", file=sys.stderr)
        return 2
    if args.criterion is not None and args.all_criteria:
        print("aide progress accept: pass --criterion or --all, not both", file=sys.stderr)
        return 2
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    progress_path = docs_dir(repo_root, config) / "progress.md"
    if not progress_path.is_file():
        print(f"error: {progress_path} not found", file=sys.stderr)
        return 1
    text = progress_path.read_text(encoding=_ENCODING)
    criteria = None if args.all_criteria else [args.criterion]
    try:
        updated, messages = accept_criteria(text, str(args.number), criteria, args.evidence)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for msg in messages:
        print(f"stage {args.number}: {msg}")
    if updated == text:
        return 0
    progress_path.write_text(updated, encoding="utf-8")
    if not args.no_commit and (repo_root / ".git").exists():
        what = "all criteria" if args.all_criteria else f"criterion {args.criterion}"
        _commit_progress_file(
            repo_root, config, f"progress(aide): stage {args.number} accept {what}")
    return 0


def _commit_progress(repo_root: Path, config, number: int, status: str) -> None:
    _commit_progress_file(
        repo_root, config, f"progress(aide): item {number:03d} -> {status}")


def _commit_progress_file(repo_root: Path, config, message: str) -> None:
    rel = str(config["project"].get("docs_dir", "docs/aide")) + "/progress.md"
    _commit_docs_files(repo_root, config, message, [rel])


def _commit_docs_files(repo_root: Path, config, message: str,
                       rels: List[str], pull: bool = True) -> Optional[str]:
    """Commit exactly *rels* — repo-relative paths — with *message*.

    Returns ``None`` when every named path is in the new commit, otherwise a
    one-line reason it is not — so a caller that announces a commit announces
    what happened, not what it intended. "Exactly" is enforced by pathspec:
    ``git commit -- <rels>`` commits the named paths and nothing else, so a
    builder's staged work sitting in the index stays staged and out of the
    bookkeeping commit; a bare ``git commit`` would have swept it in, which is
    why ``git add <rel>`` alone was never enough.

    A commit that fails — no ``user.name`` on a fresh clone, a hook, a path
    ``.gitignore`` reaches — leaves *rels* unstaged again, so the tree degrades
    to "modified" or "untracked" rather than "staged": ``aide sync`` refuses
    either, but a caller can say which and why. A ``git`` that cannot be run
    at all is a reason, not a traceback; ``check`` in particular must keep
    passing in a repo whose ``git`` is off PATH, as it did before 1.26.0.

    *pull* rebases onto the upstream first, which is right for an edit to a
    file other machines also edit (a tick, an archive) and wrong for a file
    that did not exist a moment ago — ``ensure_insights_inbox`` passes
    ``False`` so that ``check``, a gate, never fetches on the caller's behalf.
    """
    try:
        if pull:
            git(["pull", "--rebase"], repo_root, check=False)
        for rel in rels:
            git(["add", "--", rel], repo_root, check=False)
        res = git(["commit", "-m", message, "--", *rels], repo_root, check=False)
        if res.returncode != 0:
            git(["reset", "-q", "--", *rels], repo_root, check=False)
            text = (res.stdout + res.stderr).strip()
            if "nothing to commit" in text or "no changes added" in text:
                return "nothing to commit"
            first = next((l.strip() for l in text.splitlines() if l.strip()),
                         "git commit failed")
            print(f"aide: could not commit {', '.join(rels)} — {first}",
                  file=sys.stderr)
            return first
        # One path per line, never whitespace-split: a `docs_dir` with a space
        # in it must match its own entry. `core.quotepath=false` keeps a
        # non-ASCII path literal rather than octal-escaped and quoted.
        out = git(["-c", "core.quotepath=false", "show", "--name-only",
                   "--format=", "HEAD"], repo_root, check=False).stdout
        shown = [line.strip() for line in out.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError) as exc:
        # Loud here, not only in the return: three callers (`progress set`,
        # `tick`, `archive`) discard the reason, and a verb that prints its
        # success line over an uncommitted edit is the failure this names.
        why = f"git could not be run ({exc.__class__.__name__}: {exc})"
        print(f"aide: could not commit {', '.join(rels)} — {why}", file=sys.stderr)
        return why
    missing = [r for r in rels if r not in shown]
    if missing:
        # `add` was refused (an ignored path, say) and `commit -- <path>` then
        # committed the rest of the list: a commit happened, the file is not in
        # it, and "committed" would be a lie about the one path that matters.
        return f"{', '.join(missing)} is not in the commit (ignored by .gitignore?)"
    return None


def insights_path(ddir: Path) -> Path:
    """The live inbox. One name, one place — see ``queue_name``/``item_spec_paths``."""
    return ddir / "insights.md"


#: The engine's own templates — installed as ``.aide/templates/`` beside
#: ``.aide/scripts/``, and laid out the same way in the framework's source tree,
#: so one relative step serves both. Module-level so a test can point it at a
#: directory with no template in it.
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def ensure_insights_inbox(repo_root: Path, config: Dict[str, Dict[str, object]],
                          verb: str, commit: bool = True) -> Optional[Path]:
    """Create ``insights.md`` from the template when the document set has none.

    Returns the path when a file was created, ``None`` otherwise. Idempotent
    and deliberately narrow: an existing file is never touched (not even a
    malformed one — the immutability rule, conventions.md §1), and a repo with
    no ``docs_dir`` gets nothing, since a project may adopt the CLI without
    the loop and the directory itself is project-owned.

    This is the engine's side of the §1 guarantee that capture is a plain
    append to a file that exists. Before it, every agent spec told the role to
    copy the template by hand the first time an insight needed a home — six
    restatements of one step, and the one that made every spec name
    ``templates/`` (issue #85). The copy is byte-exact: ``read_bytes`` /
    ``write_bytes`` carries a BOM or CRLF the installer may have written
    through unchanged.

    The file is committed (named path, no pull) when *commit* is set and the
    repo is one: ``aide sync`` refuses a dirty tree, so a creation left
    untracked would stall the next preflight of the very loop it serves.
    Two cases decline the commit and say so in the notice rather than
    pretend: a detached ``HEAD``, where the commit would dangle and the file
    vanish on the next checkout; and a commit git refuses or cannot run (no
    identity on a fresh clone, ``git`` off PATH) — the file then stays
    untracked and the reason is printed, for the next write verb to carry.
    In a repository with no commits yet the inbox becomes the root commit;
    that is the scaffold-time ``check`` the quickstart mandates, and a root
    commit is a fine place for a file the loop owns.
    """
    ddir = docs_dir(repo_root, config)
    if not ddir.is_dir():
        return None
    path = insights_path(ddir)
    if path.exists():
        return None
    template = _TEMPLATES_DIR / "insights.md"
    rel = _rel_display(path, repo_root)
    if not template.is_file():
        print(f"aide {verb}: {rel} is missing and could not be created — "
              f"{_rel_display(template, repo_root)} is not there, so the install "
              f"is incomplete (`python install.py --into . --check` from a "
              f"framework checkout says how)", file=sys.stderr)
        return None
    path.write_bytes(template.read_bytes())
    fate = ""
    if not commit:
        fate = ", left uncommitted (--no-commit)"
    elif (repo_root / ".git").exists():
        why = _commit_created_file(repo_root, config, rel)
        fate = (" and committed it" if why is None
                else f" but NOT committed — {why}; commit it with the next work")
    print(f"notice: created {rel} from .aide/templates/insights.md{fate} — the "
          f"insight inbox, so a capture is a plain append (conventions.md §1)")
    return path


def _commit_created_file(repo_root: Path, config, rel: str) -> Optional[str]:
    """Commit the inbox `ensure_insights_inbox` just wrote — or say why not.

    ``None`` on success, else the reason, in the same shape
    ``_commit_docs_files`` returns. The detached-``HEAD`` check lives here and
    not in the shared committer because it is a policy for a *new* file: a
    commit would succeed, dangle, and take the file with it on the next
    checkout while every message reported success.
    """
    try:
        on_branch = git(["symbolic-ref", "-q", "HEAD"], repo_root,
                        check=False).returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        return f"git could not be run ({exc.__class__.__name__}: {exc})"
    if not on_branch:
        return "HEAD is detached, so the commit would dangle"
    return _commit_docs_files(repo_root, config, "docs(aide): create the insight inbox",
                              [rel], pull=False)


def insight_archive_path(ddir: Path, quarter: str) -> Path:
    """``docs/aide/insights/archive-2026-Q3.md`` — one file per quarter.

    A directory sibling to the live file, not a suffix on it, so the live file
    keeps the exact name every role appends to and the archive can grow without
    that name ever changing.
    """
    return ddir / "insights" / f"archive-{quarter}.md"


_ARCHIVE_HEADER = (
    "# Insight Archive — {quarter}\n\n"
    "_Closed entries moved out of `insights.md` by `aide insights archive`._\n"
    "_Frozen: the claims are immutable and, unlike the live file, this one is_\n"
    "_not shape-checked — see `insight_warnings`._\n"
)


def cmd_insights(args: argparse.Namespace) -> int:
    """Read and maintain ``insights.md`` — the one living document with no verb.

    Every other document has the CLI doing its mechanical work; this one made
    each triage pass an agent reading and hand-parsing the whole file, which is
    the cost that kept triage getting deferred. ``list`` answers "what is
    outstanding" without loading the archive with it, ``tick`` performs the one
    in-place edit the immutability rule permits, and ``archive`` keeps the live
    file the size of its working set.
    """
    import datetime as _dt
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    ddir = docs_dir(repo_root, config)
    path = insights_path(ddir)
    if args.action == "list":
        # An empty backlog is an answer, not an error: `list` on a repo whose
        # document set has no inbox yet creates the inbox — the same way
        # `check` does — and reports it empty. The other two verbs edit an
        # entry, and there is no entry to edit in a file that does not exist.
        if not ddir.is_dir():
            print(f"aide insights: no {_rel_display(ddir, repo_root)}/ — this "
                  f"repo has no AIDE document set, so there is no inbox to list",
                  file=sys.stderr)
            return 2
        ensure_insights_inbox(repo_root, config, verb="insights",
                              commit=not args.no_commit)
    if not path.is_file():
        print(f"aide insights {args.action}: no {_rel_display(path, repo_root)} "
              f"— nothing to {args.action}; `aide check` creates the inbox "
              f"(conventions.md §1)", file=sys.stderr)
        return 2
    text = path.read_text(encoding=_ENCODING)
    ddir_rel = ddir.relative_to(repo_root).as_posix()

    if args.action == "list":
        return _cmd_insights_list(parse_insights(text), args)
    if args.action == "tick":
        return _cmd_insights_tick(path, text, ddir_rel, repo_root, config, args,
                                  _dt.date.today().isoformat())
    return _cmd_insights_archive(path, text, ddir, ddir_rel, repo_root, config, args)


def _cmd_insights_list(entries: List[InsightEntry], args: argparse.Namespace) -> int:
    if args.type and args.type not in _INSIGHT_TYPES:
        print(f"aide insights: --type must be one of {', '.join(_INSIGHT_TYPES)}",
              file=sys.stderr)
        return 2
    shown = [e for e in entries
             if (not args.open_only or not e.ticked)
             and (not args.type or e.type == args.type)]
    for e in shown:
        if e.type is None:
            # Nothing parsed, so render the line as it stands rather than
            # dressing it in fields this listing only guessed at.
            print(f"  {e.ordinal:>3}. ?? {e.raw}")
            continue
        # The whole marker is reprinted verbatim: "where did this come from"
        # is half of what triage routes on, and a listing that drops it — or
        # re-derives it from the item number, which can only print back the
        # single-item form — sends the reader to the file it exists to replace.
        # The trailing note is reprinted for the same reason: it carries the
        # engine version a `framework` entry is triaged against, and triage
        # reads this listing rather than the file.
        prov = (f" *({e.source + ', ' if e.source else ''}{e.date}"
                f"{', ' + e.note if e.note else ''})*") if e.date else ""
        mark = "x" if e.ticked else " "
        print(f"  {e.ordinal:>3}. [{mark}] {e.type:<10} — {e.text}{prov}"
              f"{_INSIGHT_POINTER + e.pointer if e.pointer else ''}")
        if args.trail:
            for line in e.trail:
                print(f"        {line.strip()}")
    open_entries = [e for e in entries if not e.ticked]
    by_type = {t: sum(1 for e in open_entries if e.type == t) for t in _INSIGHT_TYPES}
    breakdown = ", ".join(f"{n} {t}" for t, n in by_type.items() if n)
    malformed = sum(1 for e in entries if e.type is None)
    print(f"aide insights: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, "
          f"{len(open_entries)} open"
          f"{' (' + breakdown + ')' if breakdown else ''}"
          f"{f'; {malformed} malformed — see `aide check`' if malformed else ''}")
    if len(shown) != len(entries):
        print(f"aide insights: {len(shown)} shown by the filters given")
    return 0


def _cmd_insights_tick(path: Path, text: str, ddir_rel: str, repo_root: Path,
                       config, args: argparse.Namespace, today: str) -> int:
    if args.number is None:
        print("usage: aide insights tick N --pointer TEXT", file=sys.stderr)
        return 2
    if not (args.pointer or "").strip():
        print("aide insights tick: --pointer says where the claim landed — a "
              "doc, an item, an issue. A tick without one records that triage "
              "happened and loses what it decided.", file=sys.stderr)
        return 2
    try:
        updated, message = tick_insight_text(text, args.number, args.pointer.strip(),
                                             args.date or today)
    except ValueError as exc:
        print(f"aide insights tick: {exc}", file=sys.stderr)
        return 1
    path.write_text(updated, encoding="utf-8")
    print(message)
    if not args.no_commit and (repo_root / ".git").exists():
        _commit_docs_files(repo_root, config, f"docs(aide): triage insight {args.number}",
                           [f"{ddir_rel}/insights.md"])
    return 0


def _cmd_insights_archive(path: Path, text: str, ddir: Path, ddir_rel: str,
                          repo_root: Path, config, args: argparse.Namespace) -> int:
    if not _DATE_RE.match(args.before or ""):
        print("usage: aide insights archive --before YYYY-MM-DD", file=sys.stderr)
        return 2
    remaining, moved, undatable = archive_insight_text(text, args.before)
    # Before the early return: an operator whose file will not shrink needs
    # this most in the run where nothing moved at all.
    for e in undatable:
        print(f"aide insights archive: entry {e.ordinal} "
              f"(insights.md:{e.lineno}) is closed but carries no readable "
              f"date, so no --before cut can move it: {e.raw!r}", file=sys.stderr)
    if undatable:
        print(f"aide insights archive: {len(undatable)} closed entr"
              f"{'y' if len(undatable) == 1 else 'ies'} could not be dated and "
              f"stay in the live file; `aide check` names the shape rule",
              file=sys.stderr)
    if not moved:
        print(f"aide insights: nothing closed before {args.before} to archive")
        return 0
    total = 0
    for quarter in sorted(moved):
        entries = sum(1 for ln in moved[quarter] if ln.startswith("- "))
        total += entries
        print(f"  {insight_archive_path(ddir, quarter).relative_to(repo_root).as_posix()}"
              f" ← {entries} closed entr{'y' if entries == 1 else 'ies'}")
    if not args.yes:
        print(f"aide insights archive: dry run — {total} entr"
              f"{'y' if total == 1 else 'ies'} would move; re-run with --yes")
        return 0

    rels = [f"{ddir_rel}/insights.md"]
    for quarter in sorted(moved):
        apath = insight_archive_path(ddir, quarter)
        apath.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(moved[quarter]) + "\n"
        if apath.is_file():
            existing = apath.read_text(encoding=_ENCODING)
            apath.write_text(existing.rstrip("\n") + "\n" + body, encoding="utf-8")
        else:
            apath.write_text(_ARCHIVE_HEADER.format(quarter=quarter) + "\n" + body,
                             encoding="utf-8")
        rels.append(apath.relative_to(repo_root).as_posix())
    path.write_text(remaining, encoding="utf-8")
    print(f"aide insights archive: moved {total} entr{'y' if total == 1 else 'ies'}; "
          f"{len(parse_insights(remaining))} remain — their list numbers have shifted")
    if not args.no_commit and (repo_root / ".git").exists():
        _commit_docs_files(repo_root, config,
                           f"docs(aide): archive insights closed before {args.before}",
                           rels)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    if args.action == "start":
        return _queue_start(args)
    if args.action != "tidy":
        print("usage: aide queue {start|tidy} NNN", file=sys.stderr)
        return 2
    import datetime as _dt
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    qdir = docs_dir(repo_root, config) / "queue"
    target = queue_path(qdir, args.number)
    if target is None:
        print(f"error: no {queue_name(args.number)} file under {qdir}", file=sys.stderr)
        return 1
    # Supersede by the highest-numbered queue after this one.
    later = [n for n in (queue_number(p) for p in iter_queue_paths(qdir))
             if n > args.number]
    superseded_by = max(later) if later else args.number + 1
    date = args.date or _dt.date.today().isoformat()
    text = target.read_text(encoding=_ENCODING)
    target.write_text(tidy_queue_text(text, superseded_by, date), encoding="utf-8")
    print(f"{queue_name(args.number)}: marked completed "
          f"(superseded by {queue_name(superseded_by)})")
    return 0


def _queue_start(args: argparse.Namespace) -> int:
    """Create (and, off ``local`` mode, push) a queue or specs-queue branch.

    The branch half of what `claim` does for an item. It exists because
    conventions.md §3 says a raw git form is wrong wherever a verb covers it,
    and until 1.20.0 two of the three branch shapes the engine recognises were
    covered by no verb at all: the framework's own prose told an agent to type
    `git switch -c <prefix>queue-NNN`, and the regex that must later parse that
    name never saw it until something had already gone wrong. A typo did not
    fail loudly — it made `claim` infer `main_branch` as the base and merge the
    item past the queue branch, silently.

    Recording the base is the second half. `_record_branch_base` ran only at
    claim, so a queue branch had no recorded base of its own; a queue branched
    off something other than `main_branch` had to be given `--base` at every
    later call that cared.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    branch = (specs_queue_branch_name(prefix, args.number) if args.specs
              else queue_branch_name(prefix, args.number))

    base = args.base or str(config["git"].get("main_branch", "main"))
    if not _local_branch_exists(repo_root, base):
        print(f"aide queue start: base '{base}' is not a local branch — a queue "
              f"branch is branched from its base and merged back into it, so "
              f"the base must be a branch this checkout can update",
              file=sys.stderr)
        return 1
    if _local_branch_exists(repo_root, branch):
        print(f"aide queue start: {branch} already exists — switch to it rather "
              f"than recreating it", file=sys.stderr)
        return 1
    # Also on origin: another machine (or another session) already started this
    # queue. Creating it locally would succeed and the `push -u` would then fail
    # — an uncaught CalledProcessError, i.e. a raw traceback in what is meant to
    # be an unattended flow. Fail as a sentence instead.
    if mode != "local" and _has_origin(repo_root) and branch in _remote_branches(repo_root):
        print(f"aide queue start: {branch} already exists on origin — someone "
              f"has started this queue; fetch and switch to it rather than "
              f"recreating it", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"would start {branch}; base {base}")
        return 0
    # Branch FROM the base explicitly, for the reason `claim` does: with no
    # start point `switch -c` uses HEAD, which lets the branch's actual origin
    # disagree with the base it records.
    git(["switch", "-c", branch, base], repo_root)
    _record_branch_base(repo_root, branch, base)
    # `/aide-run-roadmap` (queue-planner) and `/aide-spec-queue` (spec-author,
    # spec-reviewer) start here and reach a role before any `check` runs, so
    # the inbox is guaranteed at the same point `claim` guarantees it.
    ensure_insights_inbox(repo_root, config, verb="queue start")
    if mode != "local":
        failure = _push_new_branch(repo_root, branch)
        if failure is not None:
            print(f"aide queue start: {failure}\n"
                  f"{branch} exists locally, branched from {base}, and is "
                  f"checked out — nothing is lost. Publish it with "
                  f"'git push -u origin {branch}' once the remote is "
                  f"reachable, or start over with 'git switch {base} && "
                  f"git branch -D {branch}'.", file=sys.stderr)
            return 1
    note = "" if base == str(config["git"].get("main_branch", "main")) else f" (base {base})"
    print(f"started {branch}{note}")
    return 0


# --------------------------------------------------------------------------- #
# git layer — claim / merge / env
# --------------------------------------------------------------------------- #
def venv_python(repo_root: Path, config: Dict[str, Dict[str, object]]) -> Path:
    """Resolve the venv interpreter path (Windows Scripts vs. posix bin)."""
    venv = repo_root / str(config["python"].get("venv", ".venv"))
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def resolve_test_command(repo_root: Path, config: Dict[str, Dict[str, object]]) -> List[str]:
    """The configured test command, with a leading ``python`` bound to the venv."""
    raw = str(config["python"].get("test_command", "python -m pytest")).split()
    vpy = venv_python(repo_root, config)
    if raw and raw[0] == "python" and vpy.exists():
        return [str(vpy), *raw[1:]]
    return raw


def env_status(repo_root: Path, config: Dict[str, Dict[str, object]]) -> str:
    """Return 'ok', 'missing', or 'stale' for the project venv."""
    vpy = venv_python(repo_root, config)
    if not vpy.exists():
        return "missing"
    module = str(config["python"].get("import_check", "") or "").strip()
    if not module:
        return "ok"
    res = subprocess.run([str(vpy), "-c", f"import {module}"],
                         cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "ok" if res.returncode == 0 else "stale"


def cmd_env(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)

    if getattr(args, "profile", None):
        # Evaluate a named [validation] environment profile deterministically.
        profiles = {k: str(v) for k, v in (config.get("validation") or {}).items()}
        expr = profiles.get(args.profile)
        if expr is None:
            known = ", ".join(sorted(profiles)) or "(none defined)"
            print(f"aide env: unknown profile '{args.profile}' — [validation] defines: {known}",
                  file=sys.stderr)
            return 2
        vpy = venv_python(repo_root, config)
        interpreter = str(vpy) if vpy.exists() else sys.executable
        code = f"import sys\nsys.exit(0 if ({expr}) else 1)"
        # §6: name the codec — a traceback carrying a non-ASCII path decodes
        # differently under a Windows locale, and this text is reported to a user.
        res = subprocess.run([interpreter, "-c", code], cwd=str(repo_root),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             encoding="utf-8", errors="replace")
        if res.returncode == 0:
            print(f"aide env: profile '{args.profile}' satisfied")
            return 0
        detail = (res.stderr or "").strip().splitlines()
        suffix = f" ({detail[-1]})" if detail else ""
        print(f"aide env: profile '{args.profile}' NOT satisfied{suffix} — "
              f"validation gated on it must record '❓ Unverified', never a silent pass")
        return 1

    status = env_status(repo_root, config)
    if status == "ok":
        print("aide env: OK (venv present, import succeeds)")
        return 0
    if not args.bootstrap:
        print(f"aide env: {status} — run 'python .aide/scripts/aide.py env --bootstrap' to build it")
        return 1
    venv = repo_root / str(config["python"].get("venv", ".venv"))
    bootstrap = str(config["python"].get("bootstrap", "pip install -e .[dev]")).split()
    print(f"aide env: bootstrapping {venv} …")
    subprocess.run([sys.executable, "-m", "venv", str(venv)], cwd=str(repo_root), check=True)
    vpy = venv_python(repo_root, config)
    cmd = [str(vpy), "-m", *bootstrap] if bootstrap and bootstrap[0] == "pip" else [str(vpy), *bootstrap]
    subprocess.run(cmd, cwd=str(repo_root), check=True)
    final = env_status(repo_root, config)
    print(f"aide env: bootstrap done ({final})")
    return 0 if final == "ok" else 1


def _slug(title: str, max_words: int = 5) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "-".join(words[:max_words]) or "item"


def _queue_titles(text: str) -> Dict[int, str]:
    titles: Dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"^###\s+Item\s+0*(\d+)\s*:\s*(.+?)\s*$", line)
        if m:
            titles[int(m.group(1))] = m.group(2)
    return titles


#: Marks the start of a **forward-looking** aside inside a Dependencies section
#: — later items that depend on THIS one, not items this one depends on (e.g.
#: "**Downstream:** item 099 depends on this item's CI job"). Item numbers
#: after this marker are never read as blocking dependencies: extracting every
#: "Item NNN" mention in the section without it would misread "X depends on
#: this" as "this depends on X" and block on a backward reference to a later,
#: still-open item. Authors: put such asides after this exact marker so the
#: parser (and a human skimming the section) can tell the two apart.
_DEPENDENCIES_DOWNSTREAM_MARKER_RE = re.compile(r"\*\*Downstream\b", re.IGNORECASE)

#: Marks a quoted human-gate reach ("waits on Gate 3 — `Blocks: items 119,
#: 120, 121`"). Transcribing the gate row's cell is the natural way to say
#: which gate holds this item, and the numbers in the quote are the GATE's
#: reach, not items this one depends on — read as blockers they grew edges
#: (and cycles) nobody authored. Like ``**Downstream``, the marker must be
#: DELIBERATE markup — a backticked or bold ``Blocks:`` label, the forms a
#: quoted table cell actually takes — never bare prose: "hard blocks: Items
#: 027 and 028 must land first" states real blockers, and an exclusion plain
#: English could trip would silently drop them. The pattern consumes to the
#: end of the line and no further: the quote opens no subsection, so a
#: dependency bullet on the next line must still be read (which also means a
#: reach quote must not wrap — keep it on one line, as the template says).
_DEPENDENCIES_BLOCKS_QUOTE_RE = re.compile(
    r"(?:`|\*\*)blocks\*{0,2}\s*:[^\n]*", re.IGNORECASE)


def _item_dependencies(repo_root: Path, config, number: int) -> List[int]:
    """Item numbers named in the spec's Dependencies section (best effort).

    Uses the same multi-item/range-aware, case-insensitive extraction as every
    other "does this reference item NNN" call site (`_referenced_item_numbers`)
    — a naive first-number-only regex here previously left every number after
    the first in "Items 093, 094, 095" unrecognised as a blocker. Text at or
    after a "**Downstream" marker is excluded (see
    `_DEPENDENCIES_DOWNSTREAM_MARKER_RE`), so a forward-looking "item 099
    depends on this" aside does not register as a backward blocker; likewise
    the rest of any line from a backticked or bold "Blocks:" marker on (see
    `_DEPENDENCIES_BLOCKS_QUOTE_RE`), so a quoted gate reach does not either.
    """
    idir = docs_dir(repo_root, config) / "items"
    specs = item_spec_paths(idir, number)
    if not specs:
        return []
    text = specs[0].read_text(encoding=_ENCODING)
    m = re.search(r"^##\s+Dependencies\s*$(.*?)(^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    section = m.group(1) if m else ""
    downstream = _DEPENDENCIES_DOWNSTREAM_MARKER_RE.search(section)
    if downstream is not None:
        section = section[: downstream.start()]
    section = _DEPENDENCIES_BLOCKS_QUOTE_RE.sub("", section)
    deps = set(_referenced_item_numbers(section))
    deps.discard(number)
    return sorted(deps)


def _pick_item(repo_root: Path, config, queue_text: str,
               claim_branches: List[str]) -> Optional[Tuple[int, str]]:
    """First queue item that is planned, unclaimed, and unblocked. (number, title).

    "Unblocked" covers three things: its `## Dependencies` are all under way,
    no claim branch exists for it, and **no unresolved human gate holds it**. A
    gate naming items (directly, or via `stage N`) skips just those, so the
    queue keeps producing other work; an `all` gate stops everything, which is
    the point of declaring one — a pending decision that could invalidate what
    comes next must not have the loop racing ahead of it.
    """
    ppath = docs_dir(repo_root, config) / "progress.md"
    plines = ppath.read_text(encoding=_ENCODING).splitlines() if ppath.is_file() else []
    _, _, item_status = _parse_item_status(plines) if plines else ([], [], {})
    gate_blocked, block_everything = gate_blocked_items(plines)
    if block_everything:
        return None
    # Anchored resolution, like every other branch->item call site since 1.5.0.
    # The old unanchored search read `aide/queue-016` as item 016 and
    # `aide/specs-queue-015` as item 015, marking those items permanently
    # "claimed" and therefore unclaimable — a queue branch is not an item claim.
    # This call site was missed when the shared helper landed.
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    claimed_nums = {n for n in (_branch_item_number(br, prefix) for br in claim_branches)
                    if n is not None}
    titles = _queue_titles(queue_text)
    for num in queue_item_numbers(queue_text):
        if item_status.get(num, "planned") != "planned":
            continue
        if num in claimed_nums:
            continue
        if num in gate_blocked:
            continue
        deps = _item_dependencies(repo_root, config, num)
        # 🔍 blocks like 🚧 does: an item whose PR is still open is work that is
        # not in the base, so claiming a dependent off that base would branch
        # from a tree missing the very thing the dependency provides. Under
        # `auto-merge` this window is milliseconds; under `pr` it is however
        # long the human takes, which is exactly when it matters.
        if any(item_status.get(d, "planned") in BLOCKING_STATUSES for d in deps):
            continue
        return num, titles.get(num, f"item {num}")
    return None


def _open_queue_texts(repo_root: Path, config) -> List[str]:
    """Texts of the open queues, lowest-numbered first (derived state)."""
    qdir = docs_dir(repo_root, config) / "queue"
    if not qdir.is_dir():
        return []
    item_status = _progress_item_status(repo_root, config)
    out: List[str] = []
    for path in iter_queue_paths(qdir):
        text = path.read_text(encoding=_ENCODING)
        if queue_is_open(text, item_status):
            out.append(text)
    return out


def _live_queue_text(repo_root: Path, config, number: Optional[int]) -> Optional[str]:
    """The queue to work: an explicit number, else the lowest-numbered OPEN
    queue (state derived from progress.md). Falls back to the highest queue
    declaring ``Status: Live`` only when progress.md is missing (legacy)."""
    qdir = docs_dir(repo_root, config) / "queue"
    if number is not None:
        path = queue_path(qdir, number)
        return path.read_text(encoding=_ENCODING) if path is not None else None
    if not qdir.is_dir():
        return None
    if (docs_dir(repo_root, config) / "progress.md").is_file():
        open_texts = _open_queue_texts(repo_root, config)
        return open_texts[0] if open_texts else None
    for path in sorted(iter_queue_paths(qdir), reverse=True):
        text = path.read_text(encoding=_ENCODING)
        if is_live_queue(text):
            return text
    return None


def _report_nothing_claimable(repo_root: Path, config, prefix: str,
                              candidates: List[str],
                              claim_branches: List[str]) -> int:
    """Say why `claim` found nothing, and exit non-zero when that is a defect.

    "none left" is a claim about the ground checked, not the repository
    (conventions.md §2), and `/aide-run-queue` reads it as "the queue is
    finished — stop and report". Every reason a queue can be open while
    nothing in it is offerable therefore has to be said out loud, because the
    alternative is a run that ends reporting success over work it never
    started: issue #137, where a failed push left a claim branch behind and
    the next run called the queue exhausted.

    Two of the reasons are ordinary — a claim in flight, a dependency not
    landed — and keep exit 0. An **unpublished** claim is not: it is a `claim`
    whose push failed, holding an item on evidence no other checkout can see,
    so it exits 1 and says how to finish or release it.
    """
    ppath = docs_dir(repo_root, config) / "progress.md"
    plines = ppath.read_text(encoding=_ENCODING).splitlines() if ppath.is_file() else []
    _, _, item_status = _parse_item_status(plines) if plines else ([], [], {})
    # Queue scan order, not numeric order: `_pick_item` walks the candidate
    # queues in order and each queue in its own order, so a report that
    # renumbered the items it rejected would not be describing the same walk.
    # It shows under `loop.claim_scope = "all-open"`, where sorting numerically
    # interleaves two queues that were scanned one after the other.
    scan_order: List[int] = []
    seen = set()
    titles: Dict[int, str] = {}
    for qt in candidates:
        titles.update(_queue_titles(qt))
        for n in queue_item_numbers(qt):
            if n not in seen:
                seen.add(n)
                scan_order.append(n)
    open_items = {n for n in seen
                  if item_status.get(n, "planned") == "planned"}
    open_ordered = [n for n in scan_order if n in open_items]

    # Attribute the empty result to a gate ONLY when a gate actually explains
    # it: an `all` gate, or a gate reaching an item that is still open in a
    # queue we just scanned. A gate holding unrelated items — or naming
    # nothing — is not why this run found no work, and blaming it would be a
    # false explanation, which is worse than none.
    def _reached(g):
        if g.blocks_all:
            return set(open_items)
        if g.stage is not None:
            return set(stage_item_numbers(plines, g.stage)) & open_items
        return set(g.blocks) & open_items

    relevant = [(n, g) for n, g in enumerate(human_gates(plines), start=1)
                if g.kind != "approved" and (g.blocks_all or _reached(g))]
    if relevant:
        print("none left — held by an unresolved human gate:")
        for n, g in relevant:
            held = sorted(_reached(g))
            where = "everything" if g.blocks_all else (
                f"{g.reach} — holding " + ", ".join(f"{i:03d}" for i in held))
            print(f"  gate {n}: {g.text} — blocks {where}")
        print("  A person decides these, never an agent. Once decided: "
              "aide gate approve <n> --evidence \"…\" (or gate decline <n>).")
        return 0

    if not open_items:
        print("none left")
        return 0

    # Open items, none offered. Give the reason per item, in the order
    # `_pick_item` rejects them, so the two cannot drift into disagreeing
    # about why an item was skipped.
    claimed: Dict[int, str] = {}
    for br in claim_branches:
        num = _branch_item_number(br, prefix)
        if num is not None:
            claimed.setdefault(num, br)
    stranded = {n: br for n, br
                in _unpublished_claim_branches(repo_root, config, prefix).items()
                if n in open_items}

    print(f"none left — {len(open_ordered)} item(s) still open, none claimable:")
    for num in open_ordered:
        head = f"  {num:03d} {titles.get(num, 'item ' + str(num))} —"
        br = claimed.get(num)
        if num in stranded:
            print(f"{head} claimed by {stranded[num]}, WHICH ORIGIN HAS NEVER "
                  f"SEEN — the claim's push did not land, so this item is held "
                  f"by a claim no other checkout can see")
        elif br is not None:
            print(f"{head} claimed by {br}, already in flight")
        else:
            blockers = [d for d in _item_dependencies(repo_root, config, num)
                        if item_status.get(d, "planned") in BLOCKING_STATUSES]
            if blockers:
                print(f"{head} waiting on "
                      + ", ".join(f"{d:03d} ({item_status.get(d, 'planned')})"
                                  for d in blockers))
            else:
                print(f"{head} open and unblocked, yet not offered — please "
                      f"report this")

    if stranded:
        print("  An unpublished claim is a failed 'aide claim' push, not work "
              "in flight. Publish it ('git push -u origin <branch>') or "
              "release the item ('git branch -D <branch>'), then claim again.")
        return 1
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    scope = str(config["loop"].get("claim_scope", "live-queue"))
    if mode != "local":
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    if args.queue is None and scope == "all-open":
        # Cross-queue claiming (opt-in): scan every open queue in number order.
        candidates = _open_queue_texts(repo_root, config)
    else:
        queue_text = _live_queue_text(repo_root, config, args.queue)
        candidates = [queue_text] if queue_text is not None else []
    if not candidates:
        print("aide claim: no open queue found", file=sys.stderr)
        return 1
    branches = _list_claim_branches(repo_root, prefix)
    pick = None
    for queue_text in candidates:
        pick = _pick_item(repo_root, config, queue_text, branches)
        if pick is not None:
            break
    if pick is None:
        return _report_nothing_claimable(repo_root, config, prefix,
                                         candidates, branches)
    number, title = pick
    branch = claim_branch_name(prefix, number, title)

    # What this claim branches off, and what its `merge` will return it to.
    # `switch -c` already branches from whatever is checked out, so claiming
    # from a queue branch has always branched correctly — only the merge target
    # was fixed. Inferring the base from a *recognised queue branch* (never from
    # an arbitrary branch, which would silently retarget a merge) closes that
    # half without asking every caller to pass a flag it cannot know.
    current = _current_branch(repo_root)
    base = args.base or (current if _is_queue_branch(current, prefix)
                         else str(config["git"].get("main_branch", "main")))

    if not _local_branch_exists(repo_root, base):
        print(f"aide claim: base '{base}' is not a local branch — an item is "
              f"branched from its base and merged back into it, so the base "
              f"must be a branch this checkout can update", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"would claim item {number:03d} -> {branch} ({title}); base {base}")
        return 0
    # Branch FROM the base, explicitly. `switch -c` with no start point uses
    # HEAD, which would let the branch's actual starting point disagree with
    # the base it records — claiming with `--base main` while a queue branch is
    # checked out would start from the queue branch and then merge the whole of
    # it into main. Naming the start point makes the two agree by construction.
    git(["switch", "-c", branch, base], repo_root)
    _record_branch_base(repo_root, branch, base)
    # `/aide-run-queue` reaches its roles through `sync` and this verb, never
    # through `check`, so the §1 guarantee is kept here too: on the new branch,
    # before the push, so the inbox lands with the item and the claim's own
    # base is left exactly as it was.
    ensure_insights_inbox(repo_root, config, verb="claim")
    if mode != "local":
        failure = _push_new_branch(repo_root, branch)
        if failure is not None:
            # The branch is KEPT, not rolled back. The push may have reached
            # origin before the client gave up, and deleting here would then
            # leave a remote claim branch blocking the item with nothing local
            # left to explain it. What must not happen is the half-claim
            # reading as a claim: `_pick_item` skips any item with a claim
            # branch, so before this the next run said "none left" and an
            # unattended loop finished, successfully, having built nothing.
            # `claim`, `status` and `check` all name an unpublished
            # claim now, so it cannot pass for work in flight.
            print(f"aide claim: {failure}\n"
                  f"Item {number:03d} is claimed LOCALLY ONLY: {branch} exists "
                  f"here (base {base}) and origin has never seen it, so no "
                  f"other checkout can see the claim. Publish it with "
                  f"'git push -u origin {branch}' once the remote is "
                  f"reachable, or release the item with 'git switch {base} && "
                  f"git branch -D {branch}'.", file=sys.stderr)
            return 1
    note = "" if base == str(config["git"].get("main_branch", "main")) else f" (base {base})"
    print(f"claimed item {number:03d}: {branch} — {title}{note}")
    return 0


def _find_claim_branch(repo_root: Path, prefix: str, number: int) -> Optional[str]:
    for br in _list_claim_branches(repo_root, prefix):
        if _branch_item_number(br, prefix) == number:
            return br
    return None


def _git_dir(repo_root: Path) -> Path:
    """The repository's git directory, resolved.

    Not ``repo_root / ".git"``: that is a *file* in a linked worktree or a
    submodule, so probing `.git/MERGE_HEAD` there answers "no in-progress
    merge" for every such consumer — the exact reading the caller below must
    not get wrong.
    """
    out = git(["rev-parse", "--git-dir"], repo_root, check=False).stdout.strip()
    if not out:
        return repo_root / ".git"
    path = Path(out)
    return path if path.is_absolute() else repo_root / path


#: In-progress git operations, and how git names each one's marker in the git
#: directory. `switch` and `pull --rebase` on top of any of them either refuse
#: (leaving a half-merge the loop cannot read) or rewrite commits the human is
#: mid-way through authoring.
_INTERRUPTED_OPS: Tuple[Tuple[str, str], ...] = (
    ("rebase-merge", "a rebase is in progress"),
    ("rebase-apply", "a rebase or 'git am' is in progress"),
    ("MERGE_HEAD", "a merge is in progress with conflicts unresolved"),
    ("CHERRY_PICK_HEAD", "a cherry-pick is in progress"),
    ("REVERT_HEAD", "a revert is in progress"),
)


def _dirty_paths(repo_root: Path) -> List[str]:
    """Tracked paths carrying uncommitted changes, as git reports them.

    `-z`, not plain `--porcelain`: without it git **quotes and escapes** a path
    holding a space or a non-ASCII byte — `"docs/h\303\251llo/progress.md"` —
    which is neither the path on disk nor anything a caller can compare one
    against. NUL-terminated records never quote and never escape, so a consumer
    whose docs directory has a space in it reads the same as everyone else.

    Paths are relative to the git **worktree top level**, not to the cwd and not
    to `repo_root` — git is consistent about that, and a caller resolving them
    must be too.
    """
    out = git(["status", "--porcelain", "-z"], repo_root, check=False).stdout
    fields = out.split("\0")
    paths: List[str] = []
    i = 0
    while i < len(fields):
        record, i = fields[i], i + 1
        if len(record) < 4:                     # the empty tail after the last NUL
            continue
        code, path = record[:2], record[3:]
        if code[0] in "RC":
            i += 1                              # a rename/copy's SOURCE is its own field
        if code == "??":                        # untracked — see _unsafe_tree_state
            continue
        paths.append(path)
    return paths


def _unsafe_tree_state(repo_root: Path,
                       tick_path: Optional[Path] = None) -> Optional[str]:
    """Why this tree must not be switched/pulled/merged, or None if it may be.

    `aide merge` exists so that agents do not improvise git (§3), which means a
    consumer obeying §3 has no remaining place to be careful: whatever the verb
    does unconditionally is what happens. It already refuses one adjacent
    footgun with a precise diagnosis — a base that resolves but is not a local
    branch — and this is the same class, an operation that silently produces a
    wrong result while reporting success (issue #133).

    Untracked files are deliberately NOT dirty here. They survive `switch` and
    `pull` untouched, a loop leaves them around constantly, and a merge that
    genuinely collides with one aborts with git's own message through the merge
    path below. Refusing on them would block the common case to catch nothing.
    """
    gdir = _git_dir(repo_root)
    for marker, what in _INTERRUPTED_OPS:
        if (gdir / marker).exists():
            return what
    paths = _dirty_paths(repo_root)
    if not paths:
        return None
    # The one dirty tree this verb is likely to have caused itself: `--no-commit`
    # (on `merge` or on `progress set`) writes the tick and deliberately leaves
    # it uncommitted, and the NEXT merge — of any item — then meets this check.
    # The state is genuinely unsafe (git refuses `pull --rebase` over ANY
    # unstaged change, not merely a conflicting one), so it is still a refusal;
    # what it must not be is a mystery.
    #
    # Compared as resolved paths against the worktree top, never as strings
    # against `repo_root`: `aide.toml` may sit BELOW git's top level, and there
    # git's `docs/aide/progress.md` is this repo's `sub/docs/aide/progress.md`.
    if tick_path is not None and len(paths) == 1:
        top = git(["rev-parse", "--show-toplevel"], repo_root, check=False).stdout.strip()
        try:
            is_tick = (Path(top or repo_root) / paths[0]).resolve() == tick_path.resolve()
        except OSError:                          # an unresolvable path is not the tick
            is_tick = False
        if is_tick:
            return (f"{paths[0]} carries an uncommitted status tick — a "
                    f"`--no-commit` run wrote it and left committing to you. It "
                    f"is the only change in the tree; commit or discard it")
    shown = ", ".join(paths[:3])
    more = f" (+{len(paths) - 3} more)" if len(paths) > 3 else ""
    return f"the working tree has uncommitted changes: {shown}{more}"


def _has_unpushed_merge(repo_root: Path) -> bool:
    """Does HEAD carry a merge commit its upstream has not seen?

    The one shape `git pull --rebase` must not run over: rebasing DROPS the
    merge and replays both parents' commits individually, so a conflict a human
    resolved by hand inside that merge comes back (issue #133). No upstream
    means nothing to rebase against, which is not this shape.
    """
    res = git(["rev-list", "--merges", "@{u}..HEAD"], repo_root, check=False)
    return res.returncode == 0 and bool(res.stdout.strip())


def _restore_claim_branch(repo_root: Path, branch: str, tip: str) -> None:
    """Put back a claim branch deleted ahead of a step that then failed.

    `merge` deletes the claim branch BEFORE the post-merge test run (so the run
    sees the refs a fresh clone would). Every exit after that point must
    therefore be re-runnable: without the ref, `_find_claim_branch` finds
    nothing and the retry dies at "no claim branch found" — with the work
    merged, un-ticked and unpushed, which is the state a human least wants to
    meet a refusal in.
    """
    if tip and branch not in _local_branches(repo_root):
        git(["branch", branch, tip], repo_root, check=False)


def _promote_item_to_complete(repo_root: Path, config, number: int,
                              no_commit: bool = False) -> None:
    """Record item *number* as ✅ in progress.md — best effort, never fatal.

    Deliberately quiet about a no-op: the item may already be ✅ (a re-run, or a
    consumer still driving the old `progress set NNN done` ordering), and the
    merge itself is the thing that succeeded. It is *not* quiet about a missing
    progress.md, which is a real misconfiguration — but even that must not fail
    a merge that has already landed.
    """
    progress_path = docs_dir(repo_root, config) / "progress.md"
    if not progress_path.is_file():
        print(f"aide merge: item {number:03d} merged, but {progress_path} was "
              f"not found, so its status was NOT recorded", file=sys.stderr)
        return
    text = progress_path.read_text(encoding=_ENCODING)
    updated = set_item_status(text, number, "complete")
    if updated == text:
        return
    progress_path.write_text(updated, encoding="utf-8")
    print(f"item {number:03d}: set to done (merged)")
    if not no_commit and (repo_root / ".git").exists():
        _commit_progress(repo_root, config, number, "done")


def cmd_merge(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    branch = args.branch or _find_claim_branch(repo_root, prefix, args.number)
    if not branch:
        print(f"aide merge: no claim branch found for item {args.number:03d}", file=sys.stderr)
        return 1

    # Where this item lands: --base > what the claim recorded > main_branch.
    # Hard-wiring main_branch is what forced a consumer to merge every item of a
    # queue by hand — the queue file, a roadmap deliverable and nine item specs
    # lived only on the queue branch and had to land as one reviewed PR, so each
    # item needed to merge *back into* that branch.
    main = resolve_base(repo_root, config, args.base, branch)
    if not _local_branch_exists(repo_root, main):
        detail = ("it resolves, but not to a local branch — `git switch` would "
                  "detach HEAD, and a merge into a detached HEAD updates no "
                  "branch while still reporting success"
                  if _ref_exists(repo_root, main) else "no such local branch")
        print(f"aide merge: base '{main}' cannot be merged into: {detail}. "
              f"Pass a local branch as --base.", file=sys.stderr)
        return 1

    if mode == "pr":
        failure = _push_new_branch(repo_root, branch)
        if failure is not None:
            print(f"aide merge (pr mode): {failure}\n"
                  f"Nothing else was done — item {args.number:03d} is NOT "
                  f"ticked, and no PR can be opened over a branch origin does "
                  f"not have. The work is intact on {branch}. Resolve the "
                  f"push, then re-run 'aide merge {args.number:03d}'.",
                  file=sys.stderr)
            return 1
        print(f"aide merge (pr mode): pushed {branch}. Open a PR against {main} "
              f"to land it (e.g. 'gh pr create'); merge is left to the human "
              f"review gate. Item {args.number:03d} stays 🔍 until it merges — "
              f"then run 'aide progress set {args.number:03d} done'.")
        return 0

    unsafe = _unsafe_tree_state(repo_root, docs_dir(repo_root, config) / "progress.md")
    if unsafe:
        print(f"aide merge: refusing to merge item {args.number:03d} — {unsafe}. "
              f"`git switch` and `git pull --rebase` from here rewrite or "
              f"discard work this process did not create. Finish or abort that "
              f"state first (`git rebase --abort` / `git merge --abort`, or "
              f"commit the changes), then re-run.", file=sys.stderr)
        return 1

    git(["switch", main], repo_root)

    # Already an ancestor? Then the merge is not the missing step, and doing it
    # again can only churn. This is the case that bit a consumer: a conflict
    # resolved by hand left a merge commit on the base that had not been
    # pushed, and the re-run's `pull --rebase` linearised it — dropping the
    # merge, replaying both parents, and reintroducing the very conflict the
    # human had just resolved (issue #133). Asking git first costs one call and
    # is what makes the verb re-runnable, which a loop needs it to be.
    landed = git(["merge-base", "--is-ancestor", branch, main],
                 repo_root, check=False).returncode == 0
    if landed:
        print(f"aide merge: {branch} is already merged into {main} — skipping "
              f"the merge; the tick, the push and the cleanup still run.")
    else:
        if mode != "local":
            # `--rebase` is right for a linear local divergence and WRONG over
            # an unpushed merge commit (above). `--ff-only` integrates origin
            # where it can and refuses instead of rewriting where it cannot.
            if _has_unpushed_merge(repo_root):
                ff = git(["pull", "--ff-only"], repo_root, check=False)
                if ff.returncode != 0:
                    print(f"aide merge: {main} carries a merge commit origin "
                          f"has not seen, and origin has moved on. Rebasing "
                          f"over it would linearise the merge and bring back "
                          f"the conflicts it resolved, so this verb stops "
                          f"rather than choosing for you: push that merge "
                          f"('git push'), or integrate origin by hand, then "
                          f"re-run.\n{ff.stdout}{ff.stderr}", file=sys.stderr)
                    return 1
            else:
                git(["pull", "--rebase"], repo_root, check=False)
        merge_res = git(["merge", "--no-edit", branch], repo_root, check=False)
        if merge_res.returncode != 0:
            print(f"aide merge: merge of {branch} failed:\n{merge_res.stdout}{merge_res.stderr}", file=sys.stderr)
            return 1

    # The claim branch goes BEFORE the test run, so the run sees the refs a
    # fresh clone would (issue #125). With it still present, a consumer whose
    # test command includes `aide check` got "stale claim branch … item NNN is
    # already ✅" — a failure class the item's acceptance baseline had never
    # seen, produced by nothing but this ordering. Its tip is remembered so any
    # later exit can put the branch back exactly as it was.
    branch_tip = git(["rev-parse", branch], repo_root, check=False).stdout.strip()
    # `-d` can refuse even though the work landed (e.g. `pull --rebase` rewrote
    # main so the branch tip is no longer an ancestor); this process just
    # established that the branch is merged, so escalating to -D is safe. VERIFY
    # the outcome, never assume it.
    del_res = git(["branch", "-d", branch], repo_root, check=False)
    if del_res.returncode != 0:
        del_res = git(["branch", "-D", branch], repo_root, check=False)
    local_gone = branch not in _local_branches(repo_root)

    if not args.no_test:
        cmd = resolve_test_command(repo_root, config)
        test_res = subprocess.run(cmd, cwd=str(repo_root))
        if test_res.returncode != 0:
            _restore_claim_branch(repo_root, branch, branch_tip)
            print(f"aide merge: the post-merge test run FAILED, so item "
                  f"{args.number:03d} is NOT ✅ and nothing was pushed — the "
                  f"tick and the push are what this run refuses, not the merge "
                  f"itself. {branch} is merged into {main} in THIS repository "
                  f"only, and the claim branch is back. Fix the failures on "
                  f"{main}, commit, then re-run 'merge {args.number:03d}': the "
                  f"merge is already an ancestor, so the retry only re-tests, "
                  f"ticks and pushes.", file=sys.stderr)
            return 1

    # ✅ is set HERE, by the process that just did the merge, so it always means
    # "merged" — not "an agent said so before attempting one". The validator
    # marks the item 🔍 before this call; whether it becomes ✅ is a fact about
    # git, and in `pr` mode the return above leaves it 🔍 for the human's merge.
    #
    # It must precede the push: the tick is a commit like any other, and the
    # single `git push` below is the only one that carries `main` to origin.
    # Recording it afterwards stranded it locally, so origin's progress.md
    # under-reported — and on a queue's last item nothing would ever push it.
    _promote_item_to_complete(repo_root, config, args.number,
                              getattr(args, "no_commit", False))
    remote_gone = True
    if mode != "local":
        push_res = git(["push"], repo_root, check=False)
        if push_res.returncode != 0:
            # Reported, not swallowed: a silent failure here leaves ✅ on a
            # merge origin never received, which is the same class of lie as
            # ticking an item whose tests fail. The remote claim branch is
            # deliberately NOT deleted, so the work still exists somewhere
            # other than this checkout.
            _restore_claim_branch(repo_root, branch, branch_tip)
            print(f"aide merge: item {args.number:03d} is merged and ✅ here, "
                  f"but pushing {main} to origin FAILED, so neither the merge "
                  f"nor the tick has left this repository and the claim branch "
                  f"is kept. Resolve the push, then re-run "
                  f"'merge {args.number:03d}'.\n"
                  f"{push_res.stdout}{push_res.stderr}", file=sys.stderr)
            return 1
        del_remote = git(["push", "origin", "--delete", branch], repo_root, check=False)
        remote_gone = (del_remote.returncode == 0
                       or "remote ref does not exist" in (del_remote.stderr or ""))

    if local_gone and remote_gone:
        print(f"aide merge: item {args.number:03d} merged to {main} and claim branch {branch} deleted")
    else:
        where = [] if local_gone else ["local"]
        if not remote_gone:
            where.append("remote")
        print(f"aide merge: item {args.number:03d} merged to {main}, but the "
              f"{'/'.join(where)} claim branch {branch} could NOT be deleted:\n"
              f"{(del_res.stderr or '').strip()}\n"
              f"Run 'python .aide/scripts/aide.py gc' to sweep it up.", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# sync / gc — the scripted git workflow (no exploratory git needed)
# --------------------------------------------------------------------------- #
def _local_branches(repo_root: Path) -> List[str]:
    out = git(["branch", "--format=%(refname:short)"], repo_root, check=False).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def _remote_branches(repo_root: Path) -> List[str]:
    out = git(["branch", "-r", "--format=%(refname:short)"], repo_root, check=False).stdout
    names = []
    for l in out.splitlines():
        name = l.strip()
        if name.startswith("origin/") and "HEAD" not in name:
            names.append(name.split("/", 1)[1])
    return names


def _unpublished_branches(repo_root: Path, config, prefix: str) -> List[str]:
    """Branches under *prefix* that this checkout has and origin has not.

    Read against the remote-tracking refs, so it reports what the last fetch
    saw — `claim` fetches first and `status` does too unless asked not to.

    No origin at all is deliberately *not* an exemption. Off ``local`` mode
    the engine pushes every branch it creates, so a repository with no remote
    fails every push; issue #137's own reproduction is exactly that, and a
    claim branch there is unpublished in the strongest sense — there is
    nowhere for it to have gone. ``local`` mode is the one configuration where
    an unpushed claim branch is the design rather than a failure.
    """
    if str(config["git"].get("mode", "auto-merge")) == "local":
        return []
    remote = set(_remote_branches(repo_root))
    out = [line.strip() for line
           in git(["branch", "--format=%(refname:short)"],
                  repo_root, check=False).stdout.splitlines()]
    return sorted(br for br in out if br.startswith(prefix) and br not in remote)


def _unpublished_claim_branches(repo_root: Path, config,
                                prefix: str) -> Dict[int, str]:
    """Item number -> a claim branch this checkout has that origin has not.

    Off ``local`` mode a claim is published by construction: `claim` creates
    the branch and pushes it in the same breath, and refuses out loud when the
    push does not land. So a claim branch origin has never seen is a claim
    that did not finish — visible here, invisible to every other checkout, and
    counted as a claim by `_pick_item` regardless. That is the half-claim of
    issue #137, and naming it is what stops it reading as work in flight.

    ``local`` mode is the one configuration that reports nothing: there, an
    unpushed claim branch is the design. A repository with no origin at all is
    *not* an exemption — see `_unpublished_branches`, which this narrows.
    """
    out: Dict[int, str] = {}
    for br in _unpublished_branches(repo_root, config, prefix):
        num = _branch_item_number(br, prefix)
        if num is not None:
            out.setdefault(num, br)
    return out


def _branch_item_number(branch: str, prefix: str) -> Optional[int]:
    """Item number claimed by *branch*, or None when it is not a claim branch.

    A claim branch is ``<branch_prefix>NNN-short-name`` (conventions.md §4), so
    the number must sit *immediately* after the prefix. Anchoring is what makes
    this correct: queue numbers and item numbers share one namespace with no
    syntactic marker between them, so an unanchored digit search reads
    ``aide/queue-016`` as item 016 — an unrelated, usually long-finished work
    item — and ``aide/specs-queue-015`` likewise.

    That misread is not cosmetic. ``gc`` targets any branch whose item is ✅ and
    deletes it with ``git branch -D`` plus a remote delete, independently of
    ``--merged``; under the old unanchored match that destroyed an in-flight
    queue branch, and the unreviewed queue file and item specs living only on it.
    """
    m = re.match(re.escape(prefix) + r"0*(\d+)(?:-|$)", branch)
    return int(m.group(1)) if m else None


#: Branches the framework itself tells authors to create that are deliberately
#: NOT item claims: `/aide-create-queue`'s hand-off and `/aide-run-roadmap` name
#: `<prefix>queue-NNN`, `/aide-spec-queue` names `<prefix>specs-queue-NNN`.
#: Recognised positively so they are reported as what they are, rather than
#: lumped in with a branch nothing can parse.
#:
#: Built from `_QUEUE_TOKEN`/`_SPECS_TOKEN` — the same literals the constructors
#: below and `queue_name` use — so the recogniser cannot drift from the names
#: actually produced. 1.13.0 centralised branch *parsing*; until 1.20.0 two of
#: the three shapes had no constructor at all and were typed by an agent copying
#: a string out of a markdown file, which is why the round-trip test that now
#: pins this could not previously be written.
_QUEUE_BRANCH_RE = re.compile(
    "(?:" + re.escape(_SPECS_TOKEN) + ")?" + re.escape(_QUEUE_TOKEN) + r"\d+$")


def claim_branch_name(prefix: str, number: int, title: str) -> str:
    """``<prefix>NNN-short-name`` — the branch `aide claim` creates for an item."""
    return f"{prefix}{number:03d}-{_slug(title)}"


def queue_branch_name(prefix: str, number: int) -> str:
    """``<prefix>queue-NNN`` — the branch a queue is planned and run on."""
    return f"{prefix}{queue_name(number)}"


def specs_queue_branch_name(prefix: str, number: int) -> str:
    """``<prefix>specs-queue-NNN`` — the branch a queue's specs are authored on."""
    return f"{prefix}{_SPECS_TOKEN}{queue_name(number)}"


def _is_queue_branch(branch: str, prefix: str) -> bool:
    """True when *branch* is a queue/specs-queue branch rather than a claim."""
    return (branch.startswith(prefix)
            and _QUEUE_BRANCH_RE.match(branch[len(prefix):]) is not None)


def _has_origin(repo_root: Path) -> bool:
    out = git(["remote"], repo_root, check=False).stdout
    return "origin" in out.split()


# --------------------------------------------------------------------------- #
# Base refs — what a claim branched from, and what its merge returns to
# --------------------------------------------------------------------------- #
#: Where a claim branch remembers its base. A git-config key under the branch's
#: own section, so it travels with the branch through switch/rebase and needs no
#: file in the repo. It is deliberately *local* config: the base is a fact about
#: this checkout's branching, not something to commit and share. A machine that
#: never ran the `claim` falls back to `main_branch`, and `--base` is always
#: available — nothing silently merges somewhere unexpected.
_BASE_CONFIG_KEY = "aide-base"


def _record_branch_base(repo_root: Path, branch: str, base: str) -> None:
    git(["config", f"branch.{branch}.{_BASE_CONFIG_KEY}", base],
        repo_root, check=False)


def _recorded_branch_base(repo_root: Path, branch: str) -> Optional[str]:
    if not branch:
        return None
    res = git(["config", "--get", f"branch.{branch}.{_BASE_CONFIG_KEY}"],
              repo_root, check=False)
    value = res.stdout.strip()
    return value or None


def _current_branch(repo_root: Path) -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"],
               repo_root, check=False).stdout.strip()


def _ref_exists(repo_root: Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "--quiet", ref],
               repo_root, check=False).returncode == 0


def _local_branch_exists(repo_root: Path, ref: str) -> bool:
    """True only for an existing **local branch**, not any resolvable ref.

    A base must be a local branch, and merely resolving is not enough: `git
    switch` on a tag, a raw commit or a remote-tracking ref like `origin/main`
    detaches HEAD. A merge into a detached HEAD updates no branch at all, yet
    still reports success and lets the claim branch be deleted — the work
    survives only as an unreferenced commit. So the check is on the ref's
    *kind*, not its existence.
    """
    return git(["show-ref", "--verify", "--quiet", f"refs/heads/{ref}"],
               repo_root, check=False).returncode == 0


def _remote_or_local(repo_root: Path, ref: str) -> str:
    """``origin/<ref>`` when it resolves, else *ref* unchanged.

    Used where the question is "what has this branch actually diverged from" —
    the remote-tracking ref is what CI compares against and what the branch will
    merge into, and a local ref sitting behind the work answers that wrongly.
    """
    if _has_origin(repo_root):
        remote = f"origin/{ref}"
        if _ref_exists(repo_root, remote):
            return remote
    return ref


def resolve_base(repo_root: Path, config: Dict[str, Dict[str, object]],
                 explicit: Optional[str] = None,
                 branch: Optional[str] = None) -> str:
    """The base ref for a branch: explicit ``--base`` > recorded > config.

    ``main_branch`` stays the default and is never removed as one — this only
    adds the two ways a branch can legitimately have a *different* base, which
    is what stacked work produces: a queue branch's items branch off it and must
    merge back into it, so the whole queue lands as one reviewed PR.
    """
    if explicit:
        return explicit
    if branch is None:
        branch = _current_branch(repo_root)
    recorded = _recorded_branch_base(repo_root, branch)
    if recorded:
        return recorded
    return str(config["git"].get("main_branch", "main"))


# --------------------------------------------------------------------------- #
# Scope check — a branch's diff against its item's `## Authorised paths`
# --------------------------------------------------------------------------- #
_AUTHORISED_HEADING = "## Authorised paths"
#: The two sub-lists of that section (conventions.md §1), matched case- and
#: punctuation-insensitively so `**May change:**`, `**May change**` and
#: `May change:` all read the same.
_MAY_CHANGE_LABEL = "may change"
_ASSERTS_LABEL = "asserts against"

#: Loop bookkeeping the `aide` CLI and the agent roles are mandated to write on
#: *any* item, whatever that item is about — so a change to one is never
#: evidence of scope creep, and listing them would force every spec to repeat
#: the same boilerplate bullets just to pass. Kept explicit and wildcard-free so
#: the set cannot silently grow into a scope hole:
#:
#: - ``progress.md`` — rewritten by ``aide progress set`` on every item.
#: - ``insights.md`` — the compound-engineering inbox; conventions.md §1 names
#:   appending to it as the one write allowed outside an agent's edit scope, so
#:   flagging it would punish exactly the behaviour the framework requires.
#: - ``insights/archive-*.md`` — where ``aide insights archive`` moves closed
#:   entries. The one pattern here, added deliberately rather than by widening
#:   the rule: it is bounded to a single directory *and* a single filename
#:   shape, and ``path_matches`` anchors a bare ``*`` per path segment, so it
#:   cannot reach a subdirectory or a second name. It buys nothing an attacker
#:   or a careless agent wants — only the file the verb above it writes.
#:
#: The item's own spec is authorised separately, by number, in ``cmd_scope`` —
#: the builder records Decisions & Trade-offs there on every item.
_ALWAYS_AUTHORISED = ("progress.md", "insights.md", "insights/archive-*.md")


def _always_authorised_paths(ddir_rel: str) -> Tuple[str, ...]:
    """The always-authorised names as repo-relative patterns, the spelling item
    specs use. One joiner for the three enforcement sites — the pin lint in
    `item_spec_warnings`, the overlap exclusion in `queue_spec_findings`, and
    `cmd_scope` — so what counts as loop bookkeeping cannot drift between
    them."""
    return tuple(f"{ddir_rel}/{name}" for name in _ALWAYS_AUTHORISED)


class AuthorisedPaths(NamedTuple):
    """The two lists of an item spec's ``## Authorised paths`` section."""

    may_change: List[str]
    asserts_against: List[str]


def _strip_dot_slash(path: str) -> str:
    """Drop a leading ``./``, and only that.

    Never ``lstrip("./")``, which strips leading *characters* from that set and
    so silently renames the dotfiles specs routinely authorise —
    ``.gitattributes`` to ``gitattributes``, ``.github/workflows/ci.yml`` to
    ``github/workflows/ci.yml`` — turning a declared path into one that matches
    nothing git ever reports.
    """
    while path.startswith("./"):
        path = path[2:]
    return path


def _sub_list_label(line: str) -> Optional[str]:
    """The normalised sub-list label on *line*, or None if it is not one."""
    text = line.strip().strip("*_").strip().rstrip(":").strip().lower()
    if text == _MAY_CHANGE_LABEL:
        return _MAY_CHANGE_LABEL
    if text == _ASSERTS_LABEL:
        return _ASSERTS_LABEL
    return None


def _bullet_path(line: str) -> Optional[str]:
    """The repo-relative path a section bullet declares, or None.

    A bullet is ``- `path` — why``: the path is the FIRST backtick span, never
    the whole body, because the reason that follows it is prose. Falls back to
    the text before the first dash/colon separator for a bullet written without
    backticks. Returns None for a bullet that declares no path — an unfilled
    ``{{slot}}`` (``aide check`` already errors on those, so failing here as
    well would report one authoring slip twice) or a literal "None."
    """
    stripped = line.strip()
    if not stripped or stripped[0] not in "-*+":
        return None
    body = stripped[1:].strip()
    if not body or "{{" in body:
        return None
    m = re.search(r"`([^`]+)`", body)
    if m:
        candidate = m.group(1)
    else:
        candidate = _BULLET_REASON_RE.split(body, maxsplit=1)[0]
    candidate = candidate.strip().strip("`").strip()
    if not candidate or candidate.rstrip(".").lower() == "none":
        return None
    return _strip_dot_slash(candidate)


#: Every backtick span on a line, and where a bullet's reason starts. The two
#: together locate the bullet's PATH POSITION — the run before the reason
#: separator — which is the only place a span is a path claim. `_bullet_path`
#: splits on the same separator for a bullet written without backticks, so the
#: two readings of "where the path ends" cannot drift apart.
_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
#: The dash may END the line — `- `path` —` with the reason wrapped below is a
#: common way to write a long one, and reading it as "no reason yet" would take
#: the whole reason for more path position.
_BULLET_REASON_RE = re.compile(r"\s+[—–-](?:\s+|$)|:")

#: A Markdown list marker, which `_bullet_path` tests only by its first
#: character. The lint needs the stricter form: a continuation line opening
#: `**not** in the project group …` is emphasis, not a bullet, and reading it
#: as one attributes the reason's own spans to a path it invented. The parser
#: is left alone — its looser test yields a junk pattern that matches no file,
#: while a lint that reports MORE than the parser reads is a lint nobody
#: believes twice.
_LIST_MARKER_RE = re.compile(r"[-*+]\s")


def _authorised_section_lines(text: str) -> Optional[List[str]]:
    """The lines under ``## Authorised paths``, or None when it is absent.

    One slicer for the parser and the spec-time lint below, so the lint cannot
    warn about a bullet the parser never looked at, or stay silent about one it
    did — the whole point of the warning is to describe what `aide scope` will
    actually do with the section.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _AUTHORISED_HEADING:
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start, len(lines)):
        if _ANY_HEADER_RE.match(lines[i]) and lines[i].strip() != _AUTHORISED_HEADING:
            end = i
            break
    return lines[start:end]


def _path_position(line: str) -> Tuple[str, bool]:
    """The run of *line* before its reason separator, and whether one was seen.

    Everything after the separator is the reason, and a bullet is required to
    carry one — so a backticked name there is prose about the work, not a path
    claim. Measured on two real consumers, treating it as a path claim produced
    82 and 224 findings, almost all of them identifiers and TOML keys quoted in
    reasons; the spec that *reported* issue #119 would have raised six.
    """
    m = _BULLET_REASON_RE.search(line)
    return (line[: m.start()], True) if m else (line, False)


def dropped_bullet_spans(text: str) -> List[Tuple[str, List[str]]]:
    """``(path read, spans dropped)`` for each over-full Authorised-paths bullet.

    The contract is one path per bullet (conventions.md §1 → authorised-paths),
    and until issue #119 the two ways to break it were both silent: a bullet
    listing several comma-separated `` `path` `` spans authorised only the
    first, and a path list wrapped onto a continuation line lost everything
    below the first line, since the parser only ever inspects bullet lines. The
    narrowing surfaced much later as an `aide scope` FAIL naming paths the
    spec's own prose plainly authorised — three of one item's four bullets had
    that shape.

    Only the **path position** is read: the bullet's opening line up to its
    reason separator, plus the continuation lines while no separator has been
    seen yet, which is exactly the wrapped-list shape. That limit is what makes
    the lint worth reading rather than a source of noise to page past, and it
    is a limit: a path named after the separator is not distinguishable from a
    reason that mentions a file, so a second path written there stays silent.
    The bullet is closed by a blank line, a sub-list label, or the next bullet
    — the same shape a Markdown reader sees, so an author can predict what the
    lint attributes where.

    Silently narrowing an authorisation is the worst of the three behaviours
    available, so what IS found is reported where it is authored. A *warning*,
    not an error: the bullet is legible to a human, existing specs carry the
    shape, and the remedy (split the bullet) is the author's to apply.
    """
    section = _authorised_section_lines(text)
    if section is None:
        return []
    found: List[Tuple[str, List[str]]] = []
    open_bullet: Optional[Tuple[str, List[str]]] = None
    for line in section:
        stripped = line.strip()
        if not stripped or _sub_list_label(line) is not None:
            open_bullet = None
            continue
        if _LIST_MARKER_RE.match(stripped):
            open_bullet = None
            path = _bullet_path(line)
            # A bullet the parser declines — an unfilled `{{slot}}`, a literal
            # "None." — is somebody else's finding (`aide check` errors on the
            # slot), and nothing under it was going to be read anyway.
            if path is None:
                continue
            head, reason = _path_position(stripped[1:].strip())
            entry = (path, _BACKTICK_SPAN_RE.findall(head)[1:])
            found.append(entry)
            if not reason:
                open_bullet = entry
        elif open_bullet is not None:
            head, reason = _path_position(line)
            open_bullet[1].extend(_BACKTICK_SPAN_RE.findall(head))
            if reason:
                open_bullet = None
    return [(path, dropped) for path, dropped in found if dropped]


def declares_nothing(parsed: Optional[AuthorisedPaths]) -> bool:
    """True when a spec's scope cannot be compared with anything.

    An **empty May change is not the same as nothing declared**: a
    stage-validation item legitimately changes only the loop bookkeeping every
    item may write, while still pinning the tree it validates under *Asserts
    against*. Treating that as undeclared would drop exactly the specs whose
    whole purpose is to assert — so the test is that *both* lists are empty.
    """
    return parsed is None or not (parsed.may_change or parsed.asserts_against)


def parse_authorised_paths(text: str) -> Optional[AuthorisedPaths]:
    """Parse an item spec's ``## Authorised paths`` section.

    Returns None when the section is absent — distinct from a present-but-empty
    section (``AuthorisedPaths([], [])``), because the two need different
    remedies and neither may be read as "unconstrained" (conventions.md §1).

    Bullets appearing before either sub-list label are read as **May change**,
    which is what makes the flat single-list form — the shape consumers wrote
    before the labels existed — parse correctly rather than silently empty.
    """
    section = _authorised_section_lines(text)
    if section is None:
        return None

    may_change: List[str] = []
    asserts_against: List[str] = []
    current = may_change
    for line in section:
        label = _sub_list_label(line)
        if label is not None:
            current = may_change if label == _MAY_CHANGE_LABEL else asserts_against
            continue
        path = _bullet_path(line)
        if path is not None:
            current.append(path)
    return AuthorisedPaths(may_change, asserts_against)


def path_matches(changed: str, pattern: str) -> bool:
    """True when repo-relative *changed* is covered by *pattern*.

    Three forms, per conventions.md §1:

    - ``dir/**`` — the directory and anything at any depth below it.
    - any other pattern containing ``*``, ``?`` or ``[`` — an ordinary shell
      glob matched **per path segment**, so ``tests/golden/*.json`` covers a
      JSON file in that directory but not one a level deeper. Anchoring per
      segment is the point: ``fnmatch``'s ``*`` crosses ``/`` and would quietly
      widen every glob a spec writes into a subtree wildcard.
    - anything else — an exact path.
    """
    pattern = _strip_dot_slash(pattern.strip())
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return changed == prefix or changed.startswith(prefix + "/")
    if any(ch in pattern for ch in "*?["):
        pat_parts = pattern.split("/")
        path_parts = changed.split("/")
        if len(pat_parts) != len(path_parts):
            return False
        return all(fnmatch.fnmatchcase(p, g) for p, g in zip(path_parts, pat_parts))
    return changed == pattern


def scope_findings(changed: List[str], authorised: AuthorisedPaths,
                   always: Tuple[str, ...] = ()) -> Tuple[List[str], List[str]]:
    """``(unauthorised, contradictions)`` for a branch's *changed* paths.

    A contradiction is a path the spec declared under **Asserts against** — "my
    tests pin this without changing it" — and then changed anyway. It is
    reported separately from an unauthorised path because the remedy differs:
    one widens a list, the other means an assertion in this very item is now
    asserting against state the item moved.
    """
    unauthorised = [p for p in changed
                    if not any(path_matches(p, a) for a in always)
                    and not any(path_matches(p, g) for g in authorised.may_change)]
    contradictions = [p for p in changed
                      if any(path_matches(p, g) for g in authorised.asserts_against)]
    return unauthorised, contradictions


def _scope_base_ref(repo_root: Path, config, explicit: Optional[str]) -> str:
    """The ref ``scope`` diffs against: ``--base`` > the branch's recorded base
    > ``main_branch``.

    An explicit ``--base`` is used **verbatim** — the caller named a ref, so
    silently substituting ``origin/`` for it would make ``--base main`` mean
    something the caller did not write, and leave no way to ask for the local
    ref at all. The two *derived* answers do prefer their ``origin/``
    counterpart, since neither was chosen by anyone.

    The remote-tracking preference is the footgun this exists to avoid: on a
    checkout whose local ``main`` sits behind the work, the merge-base with it
    *is* it, so every file the earlier items touched gets reported against the
    current item's spec. Consulting the recorded base first is what makes the
    verb correct on stacked work — an item claimed from a queue branch has
    diverged from *that*, not from ``main``, and diffing against ``main`` would
    report every sibling item already merged into the queue.
    """
    if explicit:
        return explicit
    return _remote_or_local(repo_root, resolve_base(repo_root, config))


def cmd_scope(args: argparse.Namespace) -> int:
    """Check that this branch's changed files stay inside the item's spec.

    The diff-time counterpart to a byte-hash "scope fence": it asserts the
    claim the fence encoded — "item N changed only these files" — once, on the
    branch, instead of enshrining it as a suite assertion that outlives its
    truth and goes red the moment a later item is authorised to touch the
    pinned file (conventions.md §1).

    Exit 0 in scope · 1 something changed outside it · 2 could not check.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))

    number = args.number
    if number is None:
        branch = _current_branch(repo_root)
        if _is_queue_branch(branch, prefix):
            print(f"aide scope: {branch} is a queue branch, not an item claim — "
                  "per-item scope is checked on each claim branch as it merges "
                  "here, and a queue branch legitimately aggregates many items' "
                  "authorised paths. Nothing to check.")
            return 0
        number = _branch_item_number(branch, prefix)
        if number is None:
            print(f"aide scope: cannot tell which item to check — branch "
                  f"'{branch}' is not {prefix}NNN-short-name. Name the item "
                  f"explicitly: aide scope NNN", file=sys.stderr)
            return 2

    idir = docs_dir(repo_root, config) / "items"
    specs = item_spec_paths(idir, number)
    if not specs:
        print(f"aide scope: no spec for item {number:03d} under {idir}",
              file=sys.stderr)
        return 2
    spec = specs[0]
    rel_spec = spec.relative_to(repo_root).as_posix()

    authorised = parse_authorised_paths(spec.read_text(encoding=_ENCODING))
    if declares_nothing(authorised):
        what = ("has no '## Authorised paths' section" if authorised is None
                else "declares no path under '## Authorised paths'")
        print(f"aide scope: {rel_spec} {what} — cannot check scope. This is "
              "reported, never passed silently: an undeclared spec is not an "
              "unconstrained one. Add the section (see conventions.md §1) and "
              "re-run.", file=sys.stderr)
        return 2

    base = _scope_base_ref(repo_root, config, args.base)
    mb = git(["merge-base", base, "HEAD"], repo_root, check=False)
    if mb.returncode != 0:
        print(f"aide scope: could not resolve a merge-base with '{base}' — "
              f"{mb.stderr.strip()}", file=sys.stderr)
        return 2
    diff = git(["diff", "--name-only", mb.stdout.strip()], repo_root, check=False)
    if diff.returncode != 0:
        print(f"aide scope: git diff failed — {diff.stderr.strip()}",
              file=sys.stderr)
        return 2

    changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
    ddir_rel = docs_dir(repo_root, config).relative_to(repo_root).as_posix()
    always = _always_authorised_paths(ddir_rel) + (rel_spec,)
    unauthorised, contradictions = scope_findings(changed, authorised, always)

    for path in contradictions:
        print(f"error: {path} changed, but {rel_spec} lists it under "
              "'Asserts against' as pinned-not-changed")
    for path in unauthorised:
        print(f"error: {path} not authorised by {rel_spec}")

    total = len(unauthorised) + len(contradictions)
    if total:
        print(f"aide scope: FAIL (item {number:03d}, {total} of {len(changed)} "
              f"changed file(s) outside scope, vs {base})")
        return 1
    print(f"aide scope: OK (item {number:03d}, {len(changed)} changed file(s) "
          f"all authorised, vs {base})")
    return 0


def _landed_review_items(repo_root: Path, config, prefix: str,
                         base: str) -> List[str]:
    """Lines naming every 🔍 item whose branch has since landed in *base*.

    In `pr` mode nothing inside the loop ever observes the merge — the human
    does it on the forge, hours or days later — so 🔍 needs a way home or it is
    a state items enter and never leave. This is that way home, and it needs no
    knowledge of what a PR is: the same content oracle `gc` uses answers "has
    this work landed?" without a forge call that would silently degrade to
    "no open PRs found" when `gh` is missing or unauthenticated.

    Reports rather than edits. `sync` is a preflight, and a preflight that
    rewrites a tracked document as a side effect is not one.
    """
    item_status = _progress_item_status(repo_root, config)
    reviewing = {n for n, st in item_status.items() if st == "in-review"}
    if not reviewing or not _has_merge_tree(repo_root):
        return []
    local = _local_branches(repo_root)
    lines: List[str] = []
    for br in sorted(_list_claim_branches(repo_root, prefix)):
        num = _branch_item_number(br, prefix)
        if num not in reviewing:
            continue
        if _branch_content_landed(repo_root, base, _gc_ref(br, local)) is True:
            lines.append(f"aide sync: item {num:03d} is 🔍 but its work is now in "
                         f"{base} — run 'python .aide/scripts/aide.py progress "
                         f"set {num:03d} done'")
    return lines


def cmd_sync(args: argparse.Namespace) -> int:
    """Deterministic preflight: fetch, verify a clean start point, land on the
    right branch. Replaces the exploratory ``git status``/``git branch``/
    ``git fetch`` sequence agents otherwise improvise before starting work.
    Exit 0 == safe to start; exit 1 prints the one reason work must not start.
    """
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    main = str(config["git"].get("main_branch", "main"))

    if mode != "local" and _has_origin(repo_root):
        res = git(["fetch", "--all", "--prune"], repo_root, check=False)
        if res.returncode != 0:
            print(f"aide sync: fetch failed — {res.stderr.strip()}", file=sys.stderr)
            return 1

    dirty = git(["status", "--porcelain"], repo_root, check=False).stdout.strip()
    if dirty:
        print("aide sync: working tree not clean — commit or stash before starting:",
              file=sys.stderr)
        print(dirty, file=sys.stderr)
        return 1

    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root, check=False).stdout.strip()

    # Bring main up to date when we're on it (safe fast-forward only).
    if branch == main and mode != "local" and _has_origin(repo_root):
        counts = git(["rev-list", "--left-right", "--count", f"{main}...origin/{main}"],
                     repo_root, check=False).stdout.split()
        if len(counts) == 2:
            ahead, behind = int(counts[0]), int(counts[1])
            if behind and not ahead:
                git(["merge", "--ff-only", f"origin/{main}"], repo_root, check=False)
                print(f"aide sync: fast-forwarded {main} ({behind} commit(s))")
            elif behind:
                print(f"aide sync: {main} has diverged from origin/{main} "
                      f"({ahead} ahead / {behind} behind) — reconcile first", file=sys.stderr)
                return 1

    if args.item is not None:
        claim = _find_claim_branch(repo_root, prefix, args.item)
        if not claim:
            print(f"aide sync: no claim branch for item {args.item:03d} — run "
                  f"'python .aide/scripts/aide.py claim' first", file=sys.stderr)
            return 1
        if branch != claim:
            res = git(["switch", claim], repo_root, check=False)
            if res.returncode != 0:
                print(f"aide sync: could not switch to {claim}:\n{res.stderr}", file=sys.stderr)
                return 1
            branch = claim
        if mode != "local" and _has_origin(repo_root) and claim in _remote_branches(repo_root):
            git(["pull", "--rebase", "origin", claim], repo_root, check=False)

    for line in _landed_review_items(repo_root, config, prefix, main):
        print(line)

    print(f"aide sync: OK — on '{branch}', tree clean"
          + ("" if mode == "local" else ", remotes fetched"))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """One-call roadmap-state report: branch + divergence, derived queue
    states, claim branches, and (best effort) open PRs — replacing the several
    manual git/gh round-trips a resuming orchestrator otherwise makes."""
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))

    if not args.no_fetch and mode != "local" and _has_origin(repo_root):
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    branch = _current_branch(repo_root)
    # Report divergence from the base this branch actually has, not always from
    # main — on stacked work the interesting distance is to the queue branch.
    main = resolve_base(repo_root, config, args.base, branch)
    line = f"branch: {branch or '(unknown)'}"
    if mode != "local" and _has_origin(repo_root):
        counts = git(["rev-list", "--left-right", "--count", f"{main}...origin/{main}"],
                     repo_root, check=False).stdout.split()
        if len(counts) == 2:
            ahead, behind = counts
            line += f" · {main}: {ahead} ahead / {behind} behind origin/{main}"
    print(f"aide status — {repo_root.name}")
    print(f"  {line}")

    dirty = git(["status", "--porcelain"], repo_root, check=False).stdout.strip()
    print(f"  tree: {'dirty (' + str(len(dirty.splitlines())) + ' path(s))' if dirty else 'clean'}")

    item_status = _progress_item_status(repo_root, config)
    qdir = docs_dir(repo_root, config) / "queue"
    live_seen = False
    if iter_queue_paths(qdir):
        for path in iter_queue_paths(qdir):
            nums = queue_item_numbers(path.read_text(encoding=_ENCODING))
            open_nums = [n for n in nums
                         if item_status.get(n, "planned")
                         in ("planned", "in-progress", "in-review")]
            if open_nums:
                tag = " (live)" if not live_seen else ""
                live_seen = True
                listed = ", ".join(f"{n:03d}" for n in open_nums)
                print(f"  {path.name}: open{tag} — {len(open_nums)}/{len(nums)} items open ({listed})")
            else:
                print(f"  {path.name}: done")
    else:
        print("  queues: none")

    # Outcome targets not yet ✅ Met — the goal-level state a summary table's
    # stage icons deliberately do not carry (conventions.md §1).
    ppath = docs_dir(repo_root, config) / "progress.md"
    if ppath.is_file():
        plines = ppath.read_text(encoding=_ENCODING).splitlines()
        for n, g in enumerate(human_gates(plines), start=1):
            if g.kind == "approved":
                continue
            reach = g.reach
            label = {"declined": "❌ declined", "awaiting": "⏳ awaiting a decision"}.get(
                g.kind, "⚠ unrecognised status")
            print(f"  gate {n}: {g.text} [blocks {reach}] — {label}")
        for t in outcome_targets(plines):
            if t.kind == "met":
                continue
            label = {"not-met": "❌ not met", "unverified": "❓ unverified"}.get(
                t.kind, "⚠ unrecognised status")
            objs = f" [{', '.join(t.objectives)}]" if t.objectives else ""
            print(f"  target: {t.text}{objs} — {label}")

    branches = _list_claim_branches(repo_root, prefix)
    # Guarded the way `run_checks` guards it: two git spawns are not worth
    # paying on every `status` in the common "claims: none" case, and the
    # windows leg spends ~13x on a spawn (issue #74).
    unpublished = (set(_unpublished_branches(repo_root, config, prefix))
                   if branches else set())
    if branches:
        for br in branches:
            num = _branch_item_number(br, prefix)
            if num is None:
                kind = "queue branch" if _is_queue_branch(br, prefix) else "unrecognised"
                extra = " — NOT on origin" if br in unpublished else ""
                print(f"  branch: {br} ({kind} — not an item claim){extra}")
                continue
            st = item_status.get(num, "planned")
            note = ""
            if st == "complete":
                note = " — STALE (item ✅; run 'aide gc')"
            elif st == "in-review":
                # Recommending `gc` here would be recommending the deletion of
                # an open PR's head branch. It is awaiting a human, not stale.
                note = " — awaiting review (merge the PR, then 'aide progress "
                note += f"set {num:03d} done')"
            # Composes with the status note rather than replacing it: a branch
            # can be both stale and unpublished, and a reader needs both.
            if br in unpublished:
                note += (f" — NOT on origin: the claim's push did not land, so "
                         f"no other checkout can see this claim "
                         f"('git push -u origin {br}' to publish it)")
            print(f"  claim: {br} (item {num:03d}: {st}){note}")
    else:
        print("  claims: none")

    for line in _landed_review_items(repo_root, config, prefix,
                                     str(config["git"].get("main_branch", "main"))):
        print("  " + line.replace("aide sync: ", ""))

    # Open PRs, best effort — informative only, silently skipped without `gh`.
    try:
        # §6: PR titles are arbitrary UTF-8 and are printed straight through.
        res = subprocess.run(["gh", "pr", "list", "--state", "open"],
                             cwd=str(repo_root), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, encoding="utf-8",
                             errors="replace", timeout=20)
        if res.returncode == 0:
            prs = res.stdout.strip()
            if prs:
                print("  open PRs:")
                for l in prs.splitlines():
                    print(f"    {l}")
            else:
                print("  open PRs: none")
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


def _merged_prefixed_branches(repo_root: Path, main: str, prefix: str) -> List[str]:
    """Prefixed local branches already merged into *main*, per git itself.

    Ancestry-based, so it misses **every** squash merge — which is the shape
    GitHub's "Squash and merge" produces. `_branch_content_landed` is the
    stronger oracle and is preferred wherever git is new enough; this remains
    the fallback on git < 2.38, where being conservative means deleting *less*.
    """
    out = git(["branch", "--merged", main, "--format=%(refname:short)"],
              repo_root, check=False).stdout
    return [l.strip() for l in out.splitlines() if l.strip().startswith(prefix)]


#: `git merge-tree --write-tree` landed in git 2.38 (Oct 2022). As of Aug 2026
#: the only realistic holdout is Ubuntu 22.04 LTS (git 2.34.1, in standard
#: support until April 2027); 24.04, Debian 12, Git for Windows, macOS CLT and
#: this repo's CI are all past it. There is deliberately **no fallback oracle**:
#: on older git `gc` refuses to delete on the ✅ ground rather than degrading to
#: a weaker test, so old git is always *more* conservative and there is one
#: oracle to keep honest rather than two.
_MERGE_TREE_MIN_GIT = (2, 38)


def _git_version(repo_root: Path) -> Optional[Tuple[int, int]]:
    """(major, minor) of the git on PATH, or None when it cannot be read."""
    out = git(["--version"], repo_root, check=False).stdout
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _has_merge_tree(repo_root: Path) -> bool:
    version = _git_version(repo_root)
    return version is not None and version >= _MERGE_TREE_MIN_GIT


def _branch_content_landed(repo_root: Path, base: str,
                           branch_ref: str) -> Optional[bool]:
    """True when merging *branch_ref* into *base* would change *base* not at all.

    The question `gc` actually needs answered before force-deleting: is this
    branch's work already in the base? `git branch --merged` answers a *different*
    question (is the tip an ancestor) and so misses every squash merge, which is
    why `gc` reaches for `-D` in the first place. `git cherry` gets a
    single-commit squash right and a multi-commit squash wrong — a false alarm on
    the exact shape "Squash and merge" produces. Measured against fixtures of all
    three shapes:

    ======================  ===============  ============  =================
    branch                  branch --merged  git cherry    merge-tree
    ======================  ===============  ============  =================
    1 commit, squashed      misses           correct       no-op
    2 commits, squashed     misses           false alarm   no-op
    genuinely unmerged      correct          correct       would change base
    ======================  ===============  ============  =================

    Comparing the merged tree to the base's own tree also stays correct after the
    base advances with unrelated work, since that work is in both sides.

    Returns None when the answer cannot be established (unreadable ref, git too
    old, unexpected output) — a caller must treat that as "do not delete", never
    as "landed".
    """
    if not _has_merge_tree(repo_root):
        return None
    # Resolve first, so an unreadable ref is reported as unmeasurable rather than
    # as content: `merge-tree` exits 1 for a bad ref exactly as it does for a
    # conflict, and mapping both to False made `gc` skip for the right reason but
    # state the wrong one — "has content not in main" about a ref it never read.
    if not _ref_exists(repo_root, branch_ref):
        return None
    res = git(["merge-tree", "--write-tree", base, branch_ref], repo_root, check=False)
    if res.returncode == 1:
        return False  # conflicts: the branch certainly carries content the base lacks
    if res.returncode != 0:
        return None
    merged = res.stdout.strip().splitlines()
    base_tree = git(["rev-parse", f"{base}^{{tree}}"], repo_root, check=False).stdout.strip()
    if not merged or not base_tree:
        return None
    return merged[0].strip() == base_tree


def _checked_out_branches(repo_root: Path) -> set:
    """Branch names `gc` must never delete because a checkout is sitting on them.

    Three ways that happens, and the guard has to cover all three or the preview
    promises a delete `--yes` cannot perform:

    - **This worktree, on a branch.** The original case.
    - **This worktree, detached.** `git rev-parse --abbrev-ref HEAD` returns the
      literal string `HEAD`, and no branch is ever equal to that — so the guard
      silently protected nothing. Detached, the thing to protect is every branch
      at the checked-out commit.
    - **Another worktree.** `git branch -D` refuses these (git's own check), so
      without asking `git worktree list` the preview lists a branch the delete
      then bounces off.
    """
    protected = set()
    # `worktree list --porcelain` names the branch of every attached worktree —
    # including this one when it is not detached — as `branch refs/heads/<name>`.
    out = git(["worktree", "list", "--porcelain"], repo_root, check=False).stdout
    for line in out.splitlines():
        if line.startswith("branch refs/heads/"):
            protected.add(line[len("branch refs/heads/"):].strip())

    name = _current_branch(repo_root)
    if name and name != "HEAD":
        protected.add(name)
        return protected
    head = git(["rev-parse", "HEAD"], repo_root, check=False).stdout.strip()
    if not head:
        return protected
    points_at = git(["branch", "--points-at", head, "--format=%(refname:short)"],
                    repo_root, check=False).stdout
    protected.update(l.strip() for l in points_at.splitlines() if l.strip())
    return protected


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many}"


def _gc_empty_notes(repo_root: Path, prefix: str, main: str,
                    merged_flag: bool, local: List[str],
                    remote: List[str]) -> List[str]:
    """Why an empty ``gc`` result may still leave cleanup available.

    Two things the bare message hides. First, the default invocation checks
    only the item ground, so a branch that no longer resolves to an item —
    every queue and specs-queue branch — is structurally invisible to it while
    ``--merged`` would take it. Second, `gc` only ever looks at branches under
    ``prefix``, so a merged branch named anything else is never considered on
    either ground.

    Returns [] when there is genuinely nothing further to say, so the common
    case stays a single terse line. The ``--merged`` probe runs only on this
    empty path, never in the normal one.
    """
    notes: List[str] = []
    if not merged_flag and (local or remote):
        extra = _merged_prefixed_branches(repo_root, main, prefix)
        if extra:
            notes.append(
                f"{_plural(len(extra), 'branch', 'branches')} under '{prefix}' "
                f"{'is' if len(extra) == 1 else 'are'} merged into {main} — "
                f"'aide gc --merged' will take {'it' if len(extra) == 1 else 'them'}")
    others = [b for b in _local_branches(repo_root)
              if not b.startswith(prefix) and b != main]
    if others:
        notes.append(
            f"{_plural(len(others), 'local branch', 'local branches')} outside "
            f"the '{prefix}' scope {'was' if len(others) == 1 else 'were'} not "
            f"considered — gc only ever manages claim branches")
    return notes


def _gc_ref(branch: str, local: List[str]) -> str:
    """The ref to measure *branch* by: the local branch, else its remote copy."""
    return branch if branch in local else f"origin/{branch}"


def cmd_gc(args: argparse.Namespace) -> int:
    """Delete claim branches whose work has landed (item ✅ in progress.md, or
    ``--merged`` branches already merged into main). Dry-run by default; pass
    ``--yes`` to delete. The one destructive verb in the CLI, so it is never
    implicit."""
    repo_root = find_repo_root(args.repo)
    config = load_config(repo_root)
    prefix = str(config["git"].get("branch_prefix", "aide/"))
    mode = str(config["git"].get("mode", "auto-merge"))
    # The `--merged` ground is "already merged into <base>", so it takes a base
    # like everything else: on stacked work the branches that have landed have
    # landed into the queue branch, and asking about `main` finds none of them.
    main = resolve_base(repo_root, config, args.base)

    if mode != "local" and _has_origin(repo_root):
        git(["fetch", "--all", "--prune"], repo_root, check=False)

    progress_path = docs_dir(repo_root, config) / "progress.md"
    item_status: Dict[int, str] = {}
    if progress_path.is_file():
        _, _, item_status = _parse_item_status(
            progress_path.read_text(encoding=_ENCODING).splitlines())

    local = [b for b in _local_branches(repo_root) if b.startswith(prefix)]
    remote = [b for b in _remote_branches(repo_root) if b.startswith(prefix)]

    # The content oracle is what makes `-D` on the ✅ ground safe; without it
    # that ground refuses outright (see `_MERGE_TREE_MIN_GIT`).
    can_measure = _has_merge_tree(repo_root)

    merged_local: List[str] = []
    if args.merged:
        merged_local = _merged_prefixed_branches(repo_root, main, prefix)

    targets: Dict[str, str] = {}  # branch -> reason
    skips: Dict[str, str] = {}    # branch -> why it is NOT acted on
    protected = _checked_out_branches(repo_root)
    for br in sorted(set(local) | set(remote)):
        # Only a positively-identified item claim is deletable on the "item is
        # ✅" ground. A queue branch shares the number namespace but not the
        # lifecycle: it aggregates many items and lands as one reviewed PR, so
        # deleting it because some same-numbered item finished would discard
        # unreviewed work. It stays eligible under --merged, where the ground
        # is "already merged into main" and is checked against git itself.
        num = _branch_item_number(br, prefix)
        if num is not None and item_status.get(num) == "complete":
            reason = f"item {num:03d} is ✅"
            # `progress.md` is a document, edited by agents and humans; git is
            # the authority on whether the commits landed, and until 1.20.0 it
            # was never asked. A ✅ can outrun the merge easily — a commit added
            # after the validator marked it done, a hand-edit, the `pr`-mode
            # window — and the action here is `git branch -D` plus a remote
            # delete, where the remote half is unrecoverable on a plain git host.
            if args.abandon:
                targets[br] = reason + "; --abandon"
            elif not can_measure:
                skips[br] = (f"{reason}, but this git cannot verify the work "
                             f"landed (needs "
                             f"{_MERGE_TREE_MIN_GIT[0]}.{_MERGE_TREE_MIN_GIT[1]}+ "
                             f"for 'merge-tree --write-tree'); use --merged or "
                             f"--abandon")
            else:
                landed = _branch_content_landed(repo_root, main, _gc_ref(br, local))
                if landed is True:
                    targets[br] = reason
                elif landed is False:
                    skips[br] = (f"{reason} but the branch has content not in "
                                 f"{main}; re-check it, or pass --abandon to "
                                 f"delete it anyway")
                else:
                    # Not the same statement, and this is the one destructive
                    # verb: say the measurement failed, not that the branch
                    # carries work it may not carry.
                    skips[br] = (f"{reason}, but whether its work is in {main} "
                                 f"could not be determined (ref "
                                 f"'{_gc_ref(br, local)}' unreadable); not "
                                 f"deleting — pass --abandon to delete anyway")
        elif br in merged_local:
            targets[br] = f"merged into {main}"
        elif (args.merged and can_measure
              and _branch_content_landed(repo_root, main, _gc_ref(br, local)) is True):
            # `--merged` is built on `git branch --merged`, which is ancestry-
            # based and so misses every squash merge — the very shape `-D` was
            # reached for. The same oracle that guards the ✅ ground closes that.
            targets[br] = f"content already in {main}"

    if not targets and not skips:
        # "Nothing to clean" is a claim about the ground and the scope this run
        # actually checked, not about the repository — say which. The default
        # invocation checks only the item ground, and every invocation ignores
        # branches outside `prefix` (deliberately: gc is the one destructive
        # verb and must not delete branches it does not own). Left unqualified,
        # the message reads as "no cleanup is available here" and the next
        # reach is the raw `git branch -d` the CLI exists to replace.
        print("aide gc: nothing to clean")
        for note in _gc_empty_notes(repo_root, prefix, main, args.merged, local, remote):
            print(f"  {note}")
        return 0

    # Every skip is decided BEFORE anything is printed, so the preview is the
    # set `--yes` acts on rather than a promise it then quietly narrows. A dry
    # run that overstates trains the reader to skim it, and this is the one
    # destructive verb — the list a human is asked to approve must be exact.
    for br in [b for b in targets if b in protected]:
        del targets[br]
        skips[br] = ("checked out (here or in another worktree) — git refuses to "
                     "delete a branch a checkout is sitting on")

    def _where(br: str) -> str:
        return ("local+remote" if br in local and br in remote
                else "local" if br in local else "remote")

    for br in sorted(skips):
        print(f"skipping {br} ({_where(br)}): {skips[br]}")
    for br, reason in targets.items():
        if not args.yes:
            print(f"would delete {br} ({_where(br)}; {reason})")
            continue
        failures: List[str] = []
        if br in local:
            # -D: a ✅/merged item's branch may have landed via squash/PR, so
            # git's ancestry-based -d safety check can refuse a branch whose
            # work is in fact on main. Safe here only because the content check
            # above already asked git whether the work landed.
            res = git(["branch", "-D", br], repo_root, check=False)
            if res.returncode != 0:
                failures.append(f"local ({(res.stderr or '').strip()})")
        if br in remote and mode != "local":
            res = git(["push", "origin", "--delete", br], repo_root, check=False)
            if res.returncode != 0:
                failures.append(f"remote ({(res.stderr or '').strip()})")
        # Report what git did, not what was asked of it. `-D` still refuses a
        # branch checked out in ANOTHER worktree, which `_checked_out_branches`
        # cannot see from here — and printing "deleted" over a refusal makes the
        # report the very thing this verb was just fixed to stop being: a claim
        # that does not match what happened.
        if failures:
            print(f"could NOT delete {br} ({_where(br)}; {reason}): "
                  f"{'; '.join(failures)}", file=sys.stderr)
        else:
            print(f"deleted {br} ({_where(br)}; {reason})")
    if not targets:
        print("aide gc: nothing to delete")
    if not args.yes and targets:
        print("aide gc: dry run — re-run with --yes to delete")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aide", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=None, help="repo root (default: search up for aide.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="consistency gate over docs/aide "
                             "(writes only a missing insights.md, from the "
                             "template, and the file --report names)")
    p_check.add_argument("--queue", type=int, default=None,
                         help="also check this queue's specs against each other "
                              "(scope overlaps, pinned state, dependency graph)")
    p_check.add_argument("--report", default=None,
                         help="with --queue: write the findings as JSON to this path")
    p_check.set_defaults(func=cmd_check)

    p_prog = sub.add_parser("progress", help="edit progress.md status / acceptance")
    p_prog.add_argument("action", choices=["set", "accept"])
    p_prog.add_argument("number", type=int,
                        help="item number (set) | stage number (accept)")
    p_prog.add_argument("status", nargs="?", default=None,
                        help="set: in-progress | in-review | done "
                             "(in-review = pushed, awaiting a human's merge)")
    p_prog.add_argument("--criterion", type=int, default=None,
                        help="accept: 1-based acceptance-criterion index within the stage")
    p_prog.add_argument("--all", action="store_true", dest="all_criteria",
                        help="accept: every acceptance criterion in the stage")
    p_prog.add_argument("--evidence", default=None,
                        help="accept: annotation appended to the ticked criterion")
    p_prog.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_prog.set_defaults(func=cmd_progress)

    p_gate = sub.add_parser("gate", help="list / resolve human gates in progress.md")
    p_gate.add_argument("action", choices=["list", "approve", "decline"])
    p_gate.add_argument("number", type=int, nargs="?", default=None,
                        help="1-based gate row (approve/decline); see `aide gate list`")
    p_gate.add_argument("--evidence", "--reason", dest="note", default=None,
                        help="decision note written into the gate's last cell")
    p_gate.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_gate.set_defaults(func=cmd_gate)

    p_queue = sub.add_parser("queue", help="queue branch creation / maintenance")
    p_queue.add_argument("action", choices=["start", "tidy"])
    p_queue.add_argument("number", type=int)
    p_queue.add_argument("--specs", action="store_true",
                         help="start: create the specs-queue branch instead")
    p_queue.add_argument("--base", default=None,
                         help="start: branch from this ref (default: main_branch)")
    p_queue.add_argument("--dry-run", action="store_true",
                         help="start: print what would be created, create nothing")
    p_queue.add_argument("--date", default=None, help="tidy: override the supersede date (YYYY-MM-DD)")
    p_queue.set_defaults(func=cmd_queue)

    p_ins = sub.add_parser("insights", help="list / tick / archive the insight inbox")
    p_ins.add_argument("action", choices=["list", "tick", "archive"])
    p_ins.add_argument("number", type=int, nargs="?", default=None,
                       help="tick: the entry number from `insights list`")
    p_ins.add_argument("--open", action="store_true", dest="open_only",
                       help="list: only entries still untriaged")
    p_ins.add_argument("--type", default=None,
                       help="list: one of " + ", ".join(_INSIGHT_TYPES))
    p_ins.add_argument("--trail", action="store_true",
                       help="list: also print each entry's status trail")
    p_ins.add_argument("--pointer", default=None,
                       help="tick: where the claim landed (a doc, item, or issue)")
    p_ins.add_argument("--before", default=None,
                       help="archive: move entries closed before this date (YYYY-MM-DD)")
    p_ins.add_argument("--date", default=None,
                       help="tick: override the trail-line date (default: today)")
    p_ins.add_argument("--yes", action="store_true",
                       help="archive: actually move (default: dry run)")
    p_ins.add_argument("--no-commit", action="store_true", help="edit only, do not git commit")
    p_ins.set_defaults(func=cmd_insights)

    register_git_subcommands(sub)  # claim / merge / env (git layer)
    return parser


def register_git_subcommands(sub) -> None:
    """Attach the claim / merge / env subparsers (git layer)."""
    p_claim = sub.add_parser("claim", help="pick + claim the next unclaimed 📋 item")
    p_claim.add_argument("--queue", type=int, default=None,
                         help="queue number (default: the lowest-numbered open queue)")
    p_claim.add_argument("--base", default=None,
                         help="branch this claim off, and merge it back into "
                              "(default: the current branch when it is a queue "
                              "branch, else main_branch)")
    p_claim.add_argument("--dry-run", action="store_true", help="print the pick, do not create/push a branch")
    p_claim.set_defaults(func=cmd_claim)

    p_merge = sub.add_parser("merge", help="merge a validated item per git.mode")
    p_merge.add_argument("number", type=int)
    p_merge.add_argument("branch", nargs="?", default=None, help="claim branch (default: found from number)")
    p_merge.add_argument("--base", default=None,
                         help="merge into this ref (default: what the claim "
                              "recorded, else main_branch)")
    p_merge.add_argument("--no-test", action="store_true", help="skip the post-merge test run")
    p_merge.add_argument("--no-commit", action="store_true",
                         help="do not commit the progress.md status the merge records")
    p_merge.set_defaults(func=cmd_merge)

    p_env = sub.add_parser("env", help="venv existence / import check + bootstrap")
    p_env.add_argument("--bootstrap", action="store_true", help="create + populate the venv if missing/stale")
    p_env.add_argument("--profile", default=None,
                       help="evaluate a named [validation] environment profile (exit 0 iff satisfied)")
    p_env.set_defaults(func=cmd_env)

    p_sync = sub.add_parser("sync", help="preflight: fetch, verify clean tree, land on the right branch")
    p_sync.add_argument("--item", type=int, default=None,
                        help="verify/switch to this item's claim branch")
    p_sync.set_defaults(func=cmd_sync)

    p_gc = sub.add_parser("gc", help="delete claim branches whose work has landed (dry-run by default)")
    p_gc.add_argument("--merged", action="store_true",
                      help="also delete claim branches already merged into the base")
    p_gc.add_argument("--base", default=None,
                      help="ref --merged is measured against (default: the "
                           "current branch's recorded base, else main_branch)")
    p_gc.add_argument("--abandon", action="store_true",
                      help="delete a ✅ item's branch even though its content "
                           "is not in the base — for a genuinely abandoned claim")
    p_gc.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    p_gc.set_defaults(func=cmd_gc)

    p_status = sub.add_parser("status", help="one-call roadmap-state report (branch, queues, claims, PRs)")
    p_status.add_argument("--no-fetch", action="store_true", help="skip the fetch --all --prune preflight")
    p_status.add_argument("--base", default=None,
                          help="ref to report ahead/behind against (default: the "
                               "current branch's recorded base, else main_branch)")
    p_status.set_defaults(func=cmd_status)

    p_scope = sub.add_parser("scope",
                             help="check this branch's diff against the item's authorised paths")
    p_scope.add_argument("number", type=int, nargs="?", default=None,
                         help="item number (default: read from the current claim branch)")
    p_scope.add_argument("--base", default=None,
                         help="base ref to diff against (default: the branch's "
                              "recorded base, else <main_branch>; derived answers "
                              "prefer origin/<base>, falling back to the local ref)")
    p_scope.set_defaults(func=cmd_scope)


def main(argv: Optional[List[str]] = None) -> int:
    # Windows consoles often default to a non-UTF-8 codepage (cp1252), where
    # printing a status icon raises UnicodeEncodeError and kills the command
    # instead of reporting. Reconfigure once here so no caller ever needs the
    # PYTHONIOENCODING env-var dance.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        # A broken aide.toml is a user-fixable state, not a crash. Every
        # subcommand loads the config, so catching it once here keeps the
        # traceback off the screen for all of them.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
